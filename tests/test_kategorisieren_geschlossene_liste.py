"""Regel: Geschlossene Kategorienliste. Off-list -> Fallback + unsicher."""

from angebote.config import FALLBACK_GRUPPE, PRODUKTGRUPPEN
from angebote.kategorisieren import kategorisiere
from tests.fakes import FakeKategorisierer, beispiel_angebot


def test_erfundene_gruppe_wird_nicht_uebernommen():
    # Das Modell "erfindet" eine Gruppe -> Code zwingt sie in den Fallback.
    fake = FakeKategorisierer(
        lambda posten: [
            {"id": p["id"], "gruppe": "Weltraumzeug", "unsicher": False} for p in posten
        ]
    )
    ergebnis = kategorisiere([beispiel_angebot("Mondstaub")], fake)
    assert ergebnis[0].gruppe == FALLBACK_GRUPPE
    assert ergebnis[0].unsicher is True


def test_keine_gruppe_ausserhalb_der_config():
    namen = ["Butter", "Apfel", "Cola", "Bier", "Pizza", "Shampoo", "Bohrmaschine"]
    fake = FakeKategorisierer(
        # Mischung aus gültigen und ungültigen Gruppen:
        lambda posten: [
            {
                "id": p["id"],
                "gruppe": "Obst & Gemüse" if i % 2 == 0 else "Quatschgruppe",
                "unsicher": False,
            }
            for i, p in enumerate(posten)
        ]
    )
    ergebnis = kategorisiere([beispiel_angebot(n) for n in namen], fake)
    for ka in ergebnis:
        assert ka.gruppe in PRODUKTGRUPPEN
