"""Regel: Daten sind unantastbar. Preis/Gültigkeit/Händler bleiben identisch."""

from dataclasses import replace

from angebote.kategorisieren import kategorisiere
from tests.fakes import FakeKategorisierer, beispiel_angebot


def _gib_gruppe(gruppe):
    return FakeKategorisierer(
        lambda posten: [{"id": p["id"], "gruppe": gruppe, "unsicher": False} for p in posten]
    )


def test_originaldaten_unveraendert_property():
    angebote = [
        beispiel_angebot("Butter", preis=1.49, haendler="REWE"),
        beispiel_angebot("Hähnchen", preis=None, haendler="Penny", marke=None),
        beispiel_angebot("Wein", preis=4.99, haendler="EDEKA", menge="0,75 l"),
    ]
    ergebnis = kategorisiere(angebote, _gib_gruppe("Sonstiges"))

    nach = {k.angebot.angebot_id: k.angebot for k in ergebnis}
    for vorher in angebote:
        nachher = nach[vorher.angebot_id]
        # Property über den ganzen Stream: jedes belegte Feld bleibt gleich.
        assert nachher.titel == vorher.titel
        assert nachher.preis == vorher.preis
        assert nachher.haendler == vorher.haendler
        assert nachher.marke == vorher.marke
        assert nachher.menge == vorher.menge
        assert nachher.gueltig_von == vorher.gueltig_von
        assert nachher.gueltig_bis == vorher.gueltig_bis
        # Sogar Objekt-Identität: das eingefrorene Original wird durchgereicht.
        assert nachher is vorher


def test_parallel_ordnet_alle_batches_vollstaendig_zu():
    # 60 Angebote -> 3 Batches -> parallel verarbeitet; nichts darf verloren gehen.
    angebote = [beispiel_angebot(f"Artikel {i}", preis=float(i)) for i in range(60)]
    fake = FakeKategorisierer(
        lambda posten: [
            {"id": p["id"], "gruppe": "Sonstiges", "unsicher": False} for p in posten
        ]
    )
    ergebnis = kategorisiere(angebote, fake, batch_groesse=25, parallel=4)
    assert len(ergebnis) == 60
    assert all(k.gruppe == "Sonstiges" and not k.unsicher for k in ergebnis)
    # jedes Original-Angebot bleibt unverändert erhalten (id-basiert gemappt)
    ids_in = {a.angebot_id for a in angebote}
    ids_out = {k.angebot.angebot_id for k in ergebnis}
    assert ids_in == ids_out


def test_fehlender_preis_bleibt_fehlend():
    angebot = beispiel_angebot("Hähnchen", preis=None)
    ergebnis = kategorisiere([angebot], _gib_gruppe("Fleisch & Wurst"))
    assert ergebnis[0].angebot.preis is None


def test_modell_kann_daten_strukturell_nicht_aendern():
    # frozen=True: ein Versuch, den Preis zu "korrigieren", schlägt fehl.
    angebot = beispiel_angebot("Butter", preis=1.49)
    import pytest

    with pytest.raises(Exception):
        angebot.preis = 0.99  # type: ignore[misc]
    # replace erzeugt ein NEUES Objekt -- das Original bleibt unberührt.
    anderes = replace(angebot, preis=0.99)
    assert angebot.preis == 1.49 and anderes.preis == 0.99
