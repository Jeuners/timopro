"""Test-Doubles -- halten die Tests offline (kein Netz, kein LLM, kein Schlüssel)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Callable

from angebote.modell import Angebot
from angebote.quellen.basis import Ort


class FakeQuelle:
    """Adapter-Double: liefert vorgegebene Angebote, deckt-Flag, optional Fehler."""

    def __init__(self, name, angebote=None, *, deckt=True, fehler=None):
        self.name = name
        self._angebote = list(angebote or [])
        self._deckt = deckt
        self._fehler = fehler

    def deckt_ab(self, ort: Ort) -> bool:
        return self._deckt

    def hole(self, ort: Ort):
        if self._fehler is not None:
            raise self._fehler
        return list(self._angebote)


class FakeKategorisierer:
    """Kategorisierer-Double: ruft eine reine Funktion posten->antworten auf."""

    def __init__(self, fn: Callable[[list[dict]], list[dict]]):
        self._fn = fn

    def klassifiziere(self, posten: list[dict]) -> list[dict]:
        return self._fn(posten)


def beispiel_angebot(titel="Butter", **kw) -> Angebot:
    """Belegtes Angebot mit Default-Pflichtfeldern; einzeln überschreibbar."""
    daten = dict(
        titel=titel,
        haendler="REWE",
        quelle="test:fixture",
        abgerufen_am=datetime(2026, 6, 1, 8, 0, 0),
        preis=1.49,
        marke="Markenbutter",
        menge="250 g",
        gueltig_von=date(2026, 6, 1),
        gueltig_bis=date(2026, 6, 7),
    )
    daten.update(kw)
    return Angebot(**daten)
