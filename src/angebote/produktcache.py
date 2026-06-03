"""Produkt→Kategorie-Cache -- Teil des Kategorisier-Teils (Stufe 2).

Speichert pro PRODUKT-Identität (Titel + Marke, NICHT pro Angebot/Preis) die
einmal vom LLM ermittelte Produktgruppe. So muss ein bekanntes Produkt nicht
erneut eingeordnet werden -- über Zeit sinkt die LLM-Last drastisch (nur noch
*neue* Produkte gehen ans Modell), und ein günstiges Mini-Model genügt.

Schnitt-konform:
  * Es werden ausschließlich Werte gespeichert, die vom LLM stammen (Gruppe) --
    NIE Angebotsdaten (Preis/Händler/Gültigkeit). Der Cache erinnert nur an eine
    bereits getroffene Einordnung; er repariert keine Daten.
  * Er importiert KEIN LLM-Modul und keinen Kategorisier-Code (nur `config`).
  * Geschlossene Liste: Gelesen UND geschrieben werden nur Gruppen aus
    PRODUKTGRUPPEN. Eine off-list-Zeile (z. B. manipulierte DB oder geänderte
    Liste) wird beim Lesen verworfen -- selbstheilend, kein TTL nötig.
  * Nur SICHERE Zuordnungen werden abgelegt (siehe kategorisieren.py) -- so ist
    jeder Cache-Treffer per Konstruktion sicher.

Der Cache ist global (ort-/wochenübergreifend): Die Kategorie eines Produkts ist
eine objektive Eigenschaft, unabhängig von PLZ, Woche oder Modell.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import PRODUKTGRUPPEN

# Globaler Ablageort, neben dem Roh-Cache. `/data/` ist bereits in .gitignore.
STANDARD_DB = Path("data/kategorie_cache.sqlite")

_WS = re.compile(r"\s+")


def _norm(text: str | None) -> str:
    return _WS.sub(" ", (text or "").strip().lower())


def produkt_schluessel(titel: str, marke: str | None) -> str:
    """Stabile Produkt-Identität aus Titel + Marke (mengen-invariant).

    Menge bleibt bewusst draußen: 'Butter 250 g' und 'Butter 500 g' sind dieselbe
    Produktgruppe -- das maximiert die Trefferquote.
    """
    roh = _norm(titel) + "|" + _norm(marke)
    return hashlib.sha1(roh.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class CacheEintrag:
    schluessel: str
    gruppe: str
    modell: str | None
    gesehen_am: str  # ISO


class ProduktCache:
    """Schneller, persistenter Produkt→Gruppe-Cache (SQLite + In-Memory-dict).

    Beim ersten Zugriff wird die ganze (kleine) Tabelle einmalig in ein dict
    geladen -> Lookups sind O(1) im RAM, kein SQL pro Posten. Geschrieben wird
    gebündelt (`schreibe_viele`) in einer Transaktion.
    """

    def __init__(self, *, db_pfad: Path | str | None = None) -> None:
        self._pfad = Path(db_pfad) if db_pfad else STANDARD_DB
        self._mem: dict[str, str] | None = None  # lazy
        self._init_db()

    # -- intern -----------------------------------------------------------

    def _verbinde(self):
        import sqlite3

        self._pfad.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(str(self._pfad))

    def _init_db(self) -> None:
        with self._verbinde() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS produkt_kategorie ("
                "  schluessel TEXT PRIMARY KEY,"
                "  gruppe     TEXT NOT NULL,"
                "  modell     TEXT,"
                "  gesehen_am TEXT"
                ")"
            )

    def _lade(self) -> dict[str, str]:
        if self._mem is None:
            with self._verbinde() as con:
                rows = con.execute(
                    "SELECT schluessel, gruppe FROM produkt_kategorie"
                ).fetchall()
            # Whitelist auch beim Laden: nur gültige Gruppen in den Speicher.
            self._mem = {k: g for k, g in rows if g in PRODUKTGRUPPEN}
        return self._mem

    # -- öffentliche API --------------------------------------------------

    def hole(self, schluessel: str) -> str | None:
        """Gruppe für ein Produkt -- nur wenn sie in der geschlossenen Liste ist."""
        gruppe = self._lade().get(schluessel)
        return gruppe if gruppe in PRODUKTGRUPPEN else None

    def schreibe_viele(self, eintraege: list[tuple[str, str, str | None]]) -> int:
        """Speichert (schluessel, gruppe, modell)-Tupel. Nur Gruppen aus der
        geschlossenen Liste werden übernommen. Gibt die Zahl der Schreibungen."""
        gueltig = [(s, g, m) for (s, g, m) in eintraege if g in PRODUKTGRUPPEN and s]
        if not gueltig:
            return 0
        jetzt = datetime.now().isoformat()
        with self._verbinde() as con:
            con.executemany(
                "INSERT OR REPLACE INTO produkt_kategorie "
                "(schluessel, gruppe, modell, gesehen_am) VALUES (?, ?, ?, ?)",
                [(s, g, m, jetzt) for (s, g, m) in gueltig],
            )
        mem = self._lade()
        for s, g, _ in gueltig:
            mem[s] = g
        return len(gueltig)

    def groesse(self) -> int:
        return len(self._lade())
