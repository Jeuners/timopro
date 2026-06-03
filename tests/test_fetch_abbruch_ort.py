"""Regel 4: Abbruch statt stiller Drift -- mit Schwelle, Ursache, Vorschlag."""

import pytest

from angebote.fehler import AbbruchFehler
from angebote.fetch import aufloesen_ort, hole_angebote
from tests.fakes import FakeQuelle, beispiel_angebot


def test_unaufloesbarer_ort_bricht_ab():
    with pytest.raises(AbbruchFehler) as exc:
        aufloesen_ort("Hintertupfingen")
    e = exc.value
    # Der Abbruch ist brauchbar: alle drei Felder sind belegt.
    assert e.schwelle and e.ursache and e.vorschlag
    assert "PLZ" in e.vorschlag


def test_plz_wird_direkt_aufgeloest():
    ort = aufloesen_ort("60487")
    assert ort.plz == "60487"


def test_bekannter_ortsname_wird_aufgeloest():
    ort = aufloesen_ort("Frankfurt")
    assert ort.plz and ort.plz.isdigit()


def test_keine_quelle_deckt_ort_ab_bricht_ab():
    with pytest.raises(AbbruchFehler) as exc:
        hole_angebote("60487", [FakeQuelle("woanders", [], deckt=False)])
    assert exc.value.schwelle == "Ortsabdeckung"


def test_adapter_abbruch_propagiert_nicht_kaschiert():
    # Eine Quelle, die ihren Ortsbezug nicht herstellen kann, bricht ab --
    # der Orchestrator schluckt das NICHT zu einem leeren Ergebnis.
    fehler = AbbruchFehler("Quelle X", "Ortsbezug nicht verifiziert", "andere Quelle")
    quelle = FakeQuelle("kaputt", [beispiel_angebot()], fehler=fehler)
    with pytest.raises(AbbruchFehler):
        hole_angebote("60487", [quelle])
