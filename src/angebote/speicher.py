"""Persistenz der belegten Rohdaten (Stufe 1) -- deterministisch, KEIN LLM.

Trennt die zwei Stufen des Workflows auch auf der Platte:

  * Stufe 1 (Fetch) schreibt die belegten, normalisierten Angebote pro PLZ und
    Kalenderwoche hierher. Nichts wird interpretiert oder kategorisiert.
  * Stufe 2 (Kategorisieren) liest sie von hier -- sie fetcht NICHT erneut.

Bewusst rohes JSON der belegten Felder: Was die Quelle nicht hergibt, bleibt
`null` (kein Auffüllen). Die Datei belegt zusätzlich Herkunft (Quellen, geholt
am, gesehene Händler), damit der gespeicherte Stand selbst auditierbar ist.

Der Round-Trip ist verlustfrei für die belegten Felder: `lade_rohdaten`
rekonstruiert echte `Angebot`-Objekte (frozen), sodass Stufe 2 exakt mit dem
arbeitet, was Stufe 1 belegt hat.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from .modell import Angebot, FetchErgebnis

# Standard-Ablageort. Relativ zum Arbeitsverzeichnis des Servers (src/), damit
# der Pfad neben dem bestehenden Fetch-Cache (.cache/) liegt und nicht ins
# Paket eingreift. Über `basis_dir` injizierbar (Tests).
STANDARD_BASIS = Path("data/roh")


def _iso(d) -> str | None:
    return d.isoformat() if d is not None else None


def _dat(s) -> date | None:
    return date.fromisoformat(s) if s else None


def _angebot_dict(a: Angebot) -> dict:
    """Serialisiert ein belegtes Angebot vollständig -- inkl. stabiler ID."""
    return {
        "titel": a.titel,
        "haendler": a.haendler,
        "quelle": a.quelle,
        "abgerufen_am": a.abgerufen_am.isoformat(),
        "marke": a.marke,
        "preis": a.preis,
        "grundpreis": a.grundpreis,
        "menge": a.menge,
        "gueltig_von": _iso(a.gueltig_von),
        "gueltig_bis": _iso(a.gueltig_bis),
        "angebot_id": a.angebot_id,
    }


def _angebot_aus_dict(d: dict) -> Angebot:
    """Rekonstruiert ein belegtes Angebot. Fehlende Felder bleiben fehlend."""
    return Angebot(
        titel=d["titel"],
        haendler=d["haendler"],
        quelle=d["quelle"],
        abgerufen_am=datetime.fromisoformat(d["abgerufen_am"]),
        marke=d.get("marke"),
        preis=d.get("preis"),
        grundpreis=d.get("grundpreis"),
        menge=d.get("menge"),
        gueltig_von=_dat(d.get("gueltig_von")),
        gueltig_bis=_dat(d.get("gueltig_bis")),
        angebot_id=d.get("angebot_id") or "",
    )


def pfad_fuer(plz: str, *, basis_dir: Path | str | None = None, jetzt: datetime | None = None) -> Path:
    """Dateipfad pro PLZ/Kalenderwoche: data/roh/{plz}_{jahr}-W{woche}.json.

    Gleiche Wochen-Logik wie der marktguru-Cache -- so gehört der Roh-Stand
    erkennbar zur selben Woche wie die zugrundeliegende Quelle.
    """
    basis = Path(basis_dir) if basis_dir else STANDARD_BASIS
    jetzt = jetzt or datetime.now()
    jahr, woche, _ = jetzt.isocalendar()
    return basis / f"{plz}_{jahr}-W{woche:02d}.json"


def speichere_rohdaten(
    fetch: FetchErgebnis, *, basis_dir: Path | str | None = None, jetzt: datetime | None = None
) -> Path:
    """Persistiert das belegte Fetch-Ergebnis. Gibt den Schreibpfad zurück.

    KEIN LLM, kein Auffüllen: es wird exakt das geschrieben, was der Fetch belegt
    hat. `abgerufen_am` der Meta ist der Schreibzeitpunkt; die einzelnen Angebote
    tragen ihren eigenen, von der Quelle belegten Abrufzeitpunkt.
    """
    import json

    jetzt = jetzt or datetime.now()
    pfad = pfad_fuer(fetch.ort_plz, basis_dir=basis_dir, jetzt=jetzt)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    inhalt = {
        "ort_plz": fetch.ort_plz,
        "ort_name": fetch.ort_name,
        "abgerufen_am": jetzt.isoformat(),
        "abgedeckte_quellen": list(fetch.abgedeckte_quellen),
        "gesehene_haendler": list(fetch.gesehene_haendler),
        "hinweise": list(fetch.hinweise),
        "angebote": [_angebot_dict(a) for a in fetch.angebote],
    }
    pfad.write_text(json.dumps(inhalt, ensure_ascii=False, indent=2), encoding="utf-8")
    return pfad


def lade_rohdaten(
    plz: str, *, basis_dir: Path | str | None = None, jetzt: datetime | None = None
) -> FetchErgebnis | None:
    """Lädt den gespeicherten Roh-Stand der aktuellen Woche -- oder None.

    None bedeutet: für diese PLZ/Woche liegen keine Rohdaten vor (Stufe 2 ist
    dann gesperrt). Es wird NICHT gefetcht und nichts geraten.
    """
    import json

    pfad = pfad_fuer(plz, basis_dir=basis_dir, jetzt=jetzt)
    if not pfad.exists():
        return None
    d = json.loads(pfad.read_text(encoding="utf-8"))
    angebote = tuple(_angebot_aus_dict(a) for a in d.get("angebote", []))
    return FetchErgebnis(
        ort_plz=d["ort_plz"],
        ort_name=d.get("ort_name"),
        angebote=angebote,
        abgedeckte_quellen=tuple(d.get("abgedeckte_quellen", ())),
        gesehene_haendler=tuple(d.get("gesehene_haendler", ())),
        hinweise=tuple(d.get("hinweise", ())),
    )


def meta_fuer(
    plz: str, *, basis_dir: Path | str | None = None, jetzt: datetime | None = None
) -> dict | None:
    """Kurz-Zusammenfassung des Roh-Stands (für die UI), ohne die volle Liste.

    Gibt None zurück, wenn keine Rohdaten vorliegen.
    """
    import json

    pfad = pfad_fuer(plz, basis_dir=basis_dir, jetzt=jetzt)
    if not pfad.exists():
        return None
    d = json.loads(pfad.read_text(encoding="utf-8"))
    return {
        "ort_plz": d["ort_plz"],
        "ort_name": d.get("ort_name"),
        "abgerufen_am": d.get("abgerufen_am"),
        "anzahl": len(d.get("angebote", [])),
        "haendler": list(d.get("gesehene_haendler", [])),
        "quellen": list(d.get("abgedeckte_quellen", [])),
        "hinweise": list(d.get("hinweise", [])),
    }


def rohliste_dicts(fetch: FetchErgebnis) -> list[dict]:
    """Belegte Rohliste als JSON-fähige dicts -- für die UI-Anzeige von Stufe 1.

    Bewusst OHNE Produktgruppe: Stufe 1 kategorisiert nicht.
    """
    out: list[dict] = []
    for a in fetch.angebote:
        out.append(
            {
                "titel": a.titel,
                "marke": a.marke,
                "preis": a.preis,
                "grundpreis": a.grundpreis,
                "menge": a.menge,
                "haendler": a.haendler,
                "gueltig_von": _iso(a.gueltig_von),
                "gueltig_bis": _iso(a.gueltig_bis),
                "quelle": a.quelle,
            }
        )
    return out
