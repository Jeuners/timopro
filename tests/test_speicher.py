"""Persistenz der Rohdaten -- offline, deterministisch (kein Netz, kein LLM).

Geprüft wird der Architektur-Vertrag, nicht nur der Happy Path:
  * Round-Trip ist verlustfrei für belegte Felder (inkl. fehlender Felder).
  * Fehlende Felder bleiben None -- werden NICHT aufgefüllt.
  * Kein Stand -> None (Stufe 2 ist dann gesperrt), es wird nichts geraten.
  * Pfad liegt pro PLZ/Kalenderwoche.
"""

from __future__ import annotations

from datetime import date, datetime

from angebote.modell import FetchErgebnis
from angebote.speicher import (
    lade_rohdaten,
    meta_fuer,
    pfad_fuer,
    rohliste_dicts,
    speichere_rohdaten,
)
from tests.fakes import beispiel_angebot


def _fetch(angebote, plz="60487"):
    return FetchErgebnis(
        ort_plz=plz,
        ort_name=None,
        angebote=tuple(angebote),
        abgedeckte_quellen=("marktguru",),
        gesehene_haendler=tuple(sorted({a.haendler for a in angebote})),
        hinweise=("marktguru: Teilabdeckung",),
    )


def test_round_trip_behaelt_belegte_felder(tmp_path):
    a = beispiel_angebot(
        "Bio-Banane",
        haendler="ALDI SÜD",
        preis=1.29,
        marke="Bio Smiley",
        menge="1 kg",
        gueltig_von=date(2026, 6, 1),
        gueltig_bis=date(2026, 6, 7),
    )
    fetch = _fetch([a])
    pfad = speichere_rohdaten(fetch, basis_dir=tmp_path)
    assert pfad.exists()

    geladen = lade_rohdaten("60487", basis_dir=tmp_path)
    assert geladen is not None
    assert len(geladen.angebote) == 1
    g = geladen.angebote[0]
    assert g.titel == "Bio-Banane"
    assert g.haendler == "ALDI SÜD"
    assert g.preis == 1.29
    assert g.marke == "Bio Smiley"
    assert g.gueltig_von == date(2026, 6, 1)
    assert g.gueltig_bis == date(2026, 6, 7)
    # stabile ID bleibt über den Round-Trip identisch (für Stufe-2-Mapping):
    assert g.angebot_id == a.angebot_id
    # Herkunft bleibt belegt:
    assert geladen.abgedeckte_quellen == ("marktguru",)
    assert geladen.gesehene_haendler == ("ALDI SÜD",)


def test_fehlende_felder_bleiben_none_kein_auffuellen(tmp_path):
    # Pflichtfelder gesetzt, optionale bewusst leer -> dürfen NICHT geraten werden.
    a = beispiel_angebot(
        "No-Name-Artikel",
        haendler="REWE",
        preis=None,
        marke=None,
        menge=None,
        grundpreis=None,
        gueltig_von=None,
        gueltig_bis=None,
    )
    speichere_rohdaten(_fetch([a]), basis_dir=tmp_path)
    g = lade_rohdaten("60487", basis_dir=tmp_path).angebote[0]
    assert g.preis is None
    assert g.marke is None
    assert g.menge is None
    assert g.grundpreis is None
    assert g.gueltig_von is None
    assert g.gueltig_bis is None


def test_kein_stand_liefert_none(tmp_path):
    assert lade_rohdaten("12345", basis_dir=tmp_path) is None
    assert meta_fuer("12345", basis_dir=tmp_path) is None


def test_meta_fasst_zusammen(tmp_path):
    a = beispiel_angebot("Butter", haendler="REWE")
    b = beispiel_angebot("Käse", haendler="EDEKA")
    speichere_rohdaten(_fetch([a, b]), basis_dir=tmp_path)
    meta = meta_fuer("60487", basis_dir=tmp_path)
    assert meta["anzahl"] == 2
    assert set(meta["haendler"]) == {"REWE", "EDEKA"}
    assert meta["abgerufen_am"]


def test_pfad_pro_plz_und_woche():
    jetzt = datetime(2026, 6, 2, 9, 0, 0)  # ISO-Woche 23/2026
    pfad = pfad_fuer("60487", basis_dir="/tmp/roh", jetzt=jetzt)
    assert pfad.name == "60487_2026-W23.json"


def test_rohliste_ohne_produktgruppe(tmp_path):
    """Stufe 1 kategorisiert nicht -- die Rohliste trägt keine Produktgruppe."""
    a = beispiel_angebot("Butter")
    dicts = rohliste_dicts(_fetch([a]))
    assert dicts and "produktgruppe" not in dicts[0]
    assert "gruppe" not in dicts[0]
