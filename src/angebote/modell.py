"""Datenmodell des Fetch-Teils.

`Angebot` ist bewusst `frozen=True`: Der Kategorisier-Schritt soll die Daten
nicht nur nicht verändern -- er *kann* es nicht. Damit ist die Regel "Daten
sind unantastbar" eine prüfbare Eigenschaft des Typs, keine Bitte.

Es gibt bewusst KEIN Feld `produktgruppe`: Die Trennung von Beschaffung und
Einordnung ist im Datenmodell verankert (siehe SKILL angebote-fetch).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class Angebot:
    """Ein normalisiertes, belegtes Angebot.

    Pflichtfelder (`haendler`, `quelle`, `abgerufen_am`) belegen die Herkunft.
    Optionale Felder sind `None`, wenn die Quelle sie nicht eindeutig hergibt --
    niemals geraten.
    """

    titel: str
    haendler: str
    quelle: str
    abgerufen_am: datetime
    marke: str | None = None
    preis: float | None = None
    grundpreis: str | None = None
    menge: str | None = None
    gueltig_von: date | None = None
    gueltig_bis: date | None = None
    # Stabile ID für das Zurückmappen nach der Kategorisierung. Wird aus
    # belegten Feldern abgeleitet, nicht erfunden.
    angebot_id: str = ""

    def __post_init__(self) -> None:
        if not self.titel or not self.titel.strip():
            raise ValueError("Angebot ohne Titel ist nicht belegbar")
        if not self.haendler or not self.haendler.strip():
            raise ValueError("Angebot ohne Händler verletzt 'nur Belegtes'")
        if not self.quelle or not self.quelle.strip():
            raise ValueError("Angebot ohne Quelle verletzt 'nur Belegtes'")
        if not self.angebot_id:
            # frozen -> über object.__setattr__ setzen
            object.__setattr__(self, "angebot_id", self._ableiten_id())

    def _ableiten_id(self) -> str:
        import hashlib

        roh = "|".join(
            [
                self.haendler,
                self.quelle,
                self.titel,
                str(self.preis),
                str(self.gueltig_von),
                str(self.gueltig_bis),
            ]
        )
        return hashlib.sha1(roh.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class KategorisiertesAngebot:
    """Ein Angebot plus die vom LLM vergebene Gruppe.

    Das Original-`Angebot` bleibt unverändert eingebettet -- übernommen werden
    aus dem Modell ausschließlich `gruppe` und `unsicher`.
    """

    angebot: Angebot
    gruppe: str
    unsicher: bool = False


@dataclass(frozen=True)
class FetchErgebnis:
    """Ergebnis des Fetch-Teils: belegte Angebote + ehrliche Abdeckungslage."""

    ort_plz: str
    ort_name: str | None
    angebote: tuple[Angebot, ...]
    abgedeckte_quellen: tuple[str, ...]
    # Datengetrieben: die Händler, die tatsächlich in den Angeboten vorkamen.
    gesehene_haendler: tuple[str, ...] = field(default_factory=tuple)
    hinweise: tuple[str, ...] = field(default_factory=tuple)
