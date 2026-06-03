"""Web-Schicht -- offline. Struktur-Funktion + Endpoints (ohne Netz/Key/LLM).

Der Schnitt gilt auch hier: die Web-Schicht fügt keine Logik hinzu, sie ruft
die getesteten Module auf. Geprüft wird, dass sie das belegt-und-ehrlich
weiterreicht.
"""

import pytest

from angebote.modell import FetchErgebnis, KategorisiertesAngebot
from angebote.uebersicht import als_struktur
from tests.fakes import beispiel_angebot

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import angebote.web as web  # noqa: E402
from angebote.modelle import ModellInfo  # noqa: E402


def _fetch_mit(angebote):
    return FetchErgebnis(
        ort_plz="60487",
        ort_name=None,
        angebote=tuple(angebote),
        abgedeckte_quellen=("marktguru",),
        gesehene_haendler=tuple(sorted({a.haendler for a in angebote})),
        hinweise=("marktguru: Teilabdeckung",),
    )


def test_als_struktur_behaelt_belegte_felder_und_leere_gruppen():
    a = beispiel_angebot("Butter", preis=1.49, haendler="REWE")
    kat = [KategorisiertesAngebot(a, "Molkereiprodukte & Eier", unsicher=False)]
    struktur = als_struktur(_fetch_mit([a]), kat)

    assert struktur["anzahl"] == 1
    # alle 13 Produktgruppen vorhanden, leere als leere Liste (kein Weglassen):
    assert len(struktur["gruppen"]) == 13
    molk = next(g for g in struktur["gruppen"] if g["name"].startswith("Molkerei"))
    assert molk["angebote"][0]["preis"] == 1.49
    assert molk["angebote"][0]["haendler"] == "REWE"
    leere = [g for g in struktur["gruppen"] if g["anzahl"] == 0]
    assert leere  # leere Gruppen bleiben erhalten


def test_index_liefert_html():
    client = TestClient(web.app)
    r = client.get("/")
    assert r.status_code == 200
    assert "Angebots-Übersicht" in r.text


def test_api_modelle_gibt_top_free(monkeypatch):
    fake = [
        ModellInfo("moonshotai/kimi-k2.6:free", "Kimi", 262144, True, True),
        ModellInfo("anthropic/claude-sonnet-4.6", "Sonnet", 200000, False, True),
    ]
    monkeypatch.setattr(web, "_jobs", {})  # sauberer Zustand
    monkeypatch.setattr("angebote.modelle.lade_modelle", lambda session=None: fake)
    client = TestClient(web.app)
    r = client.get("/api/modelle")
    assert r.status_code == 200
    daten = r.json()
    assert daten and daten[0]["id"] == "moonshotai/kimi-k2.6:free"
    assert daten[0]["frei"] is True


def test_api_lauf_ohne_plz_ist_400():
    client = TestClient(web.app)
    r = client.post("/api/lauf", json={"plz": ""})
    assert r.status_code == 400


def test_api_status_unbekannt_ist_404():
    client = TestClient(web.app)
    r = client.get("/api/lauf/gibtsnicht")
    assert r.status_code == 404
