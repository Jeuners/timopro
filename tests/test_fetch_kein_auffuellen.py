"""Regel: Kein Auffüllen. Leeres Quellergebnis bleibt leer."""

from angebote.fetch import hole_angebote
from angebote.uebersicht import rendern
from tests.fakes import FakeQuelle


def test_leere_quelle_fuellt_nicht_auf():
    ergebnis = hole_angebote("60487", [FakeQuelle("leer", [])])
    assert ergebnis.angebote == ()
    # Der Lauf wird ehrlich vermerkt, nicht versteckt:
    assert any("0 Angebote" in h for h in ergebnis.hinweise)


def test_uebersicht_zeigt_keine_erfundenen_beispiele():
    ergebnis = hole_angebote("60487", [FakeQuelle("leer", [])])
    text = rendern(ergebnis, [])
    # Jede Gruppe steht da -- aber leer, als "keine Angebote", nicht aufgefüllt.
    assert text.count("_keine Angebote_") >= 1
    # Keine Beispieldaten:
    assert "€" not in text or "Preis fehlt" in text
