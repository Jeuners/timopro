"""Regel: Unsicherheit wird geflaggt, nicht still einsortiert."""

from angebote.kategorisieren import kategorisiere
from angebote.modell import FetchErgebnis
from angebote.uebersicht import rendern
from tests.fakes import FakeKategorisierer, beispiel_angebot


def test_mehrdeutiger_artikel_wird_geflaggt():
    fake = FakeKategorisierer(
        lambda posten: [
            {"id": p["id"], "gruppe": "Molkereiprodukte & Eier", "unsicher": True}
            for p in posten
        ]
    )
    ergebnis = kategorisiere([beispiel_angebot("Hafer-Pflanzendrink")], fake)
    assert ergebnis[0].unsicher is True


def test_nicht_beantworteter_posten_wird_unsicher_statt_still():
    # Modell antwortet zu KEINEM Posten -> kein stilles Einsortieren.
    fake = FakeKategorisierer(lambda posten: [])
    ergebnis = kategorisiere([beispiel_angebot("Rätselartikel")], fake)
    assert ergebnis[0].unsicher is True


def test_unsicherheit_ist_in_der_uebersicht_sichtbar():
    fake = FakeKategorisierer(
        lambda posten: [
            {"id": p["id"], "gruppe": "Sonstiges", "unsicher": True} for p in posten
        ]
    )
    kat = kategorisiere([beispiel_angebot("Pflanzendrink")], fake)
    fetch = FetchErgebnis(
        ort_plz="60487",
        ort_name=None,
        angebote=tuple(k.angebot for k in kat),
        abgedeckte_quellen=("test",),
    )
    text = rendern(fetch, kat)
    assert "unsicher" in text
