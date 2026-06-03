"""Tests für die manuelle Korrektur (POST /api/korrektur) + Cache-Wirkung."""

import sqlite3

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import angebote.web as web  # noqa: E402
from angebote.produktcache import ProduktCache, produkt_schluessel  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Isolierte Cache-DB; der Endpoint nutzt ProduktCache() ohne Pfad -> STANDARD_DB."""
    p = tmp_path / "kat.sqlite"
    monkeypatch.setattr("angebote.produktcache.STANDARD_DB", p)
    return p


def test_korrektur_gueltig_schreibt_cache(db):
    client = TestClient(web.app)
    r = client.post(
        "/api/korrektur",
        json={"titel": "Hafer-Drink", "marke": "Oatly", "gruppe": "Getränke (alkoholfrei)"},
    )
    assert r.status_code == 200
    assert r.json()["gespeichert"] is True
    cache = ProduktCache(db_pfad=db)
    assert cache.hole(produkt_schluessel("Hafer-Drink", "Oatly")) == "Getränke (alkoholfrei)"


def test_korrektur_off_list_ist_400(db):
    client = TestClient(web.app)
    r = client.post("/api/korrektur", json={"titel": "X", "gruppe": "Weltraumzeug"})
    assert r.status_code == 400
    assert ProduktCache(db_pfad=db).groesse() == 0


def test_korrektur_ohne_titel_ist_400(db):
    client = TestClient(web.app)
    r = client.post("/api/korrektur", json={"titel": "  ", "gruppe": "Fisch"})
    assert r.status_code == 400


def test_korrektur_modell_ist_manuell(db):
    client = TestClient(web.app)
    client.post("/api/korrektur", json={"titel": "Lachs", "marke": None, "gruppe": "Fisch"})
    with sqlite3.connect(str(db)) as con:
        row = con.execute("SELECT modell FROM produkt_kategorie").fetchone()
    assert row[0] == "manuell"


def test_manuelle_zuordnung_ist_cache_hit_kein_llm(db):
    from angebote.kategorisieren import kategorisiere
    from tests.fakes import CountingFakeKategorisierer, beispiel_angebot

    cache = ProduktCache(db_pfad=db)
    cache.schreibe_viele(
        [(produkt_schluessel("Hafer-Drink", None), "Getränke (alkoholfrei)", "manuell")]
    )
    a = beispiel_angebot("Hafer-Drink", marke=None)
    fake = CountingFakeKategorisierer("Sonstiges")  # würde falsch raten
    stat = {}
    erg = kategorisiere([a], fake, cache=cache, statistik=stat)
    assert fake.gesehen == 0  # kein LLM-Posten -- die manuelle Zuordnung gewinnt
    assert stat == {"aus_cache": 1, "neu": 0}
    assert erg[0].gruppe == "Getränke (alkoholfrei)" and not erg[0].unsicher


def test_korrektur_patcht_ergebnis_cache(db):
    client = TestClient(web.app)
    schluessel = produkt_schluessel("Toffifee", "Storck")
    key = ("99999", "openrouter", "x")
    web._ergebnis_cache[key] = {
        "gruppen": [
            {
                "name": "Sonstiges",
                "anzahl": 1,
                "angebote": [{"titel": "Toffifee", "marke": "Storck", "unsicher": True}],
            },
            {"name": "Süßwaren & Snacks", "anzahl": 0, "angebote": []},
        ],
        "unsicher": 1,
    }
    try:
        r = client.post(
            "/api/korrektur",
            json={
                "titel": "Toffifee", "marke": "Storck",
                "gruppe": "Süßwaren & Snacks", "plz": "99999",
            },
        )
        assert r.status_code == 200
        erg = web._ergebnis_cache[key]
        suess = next(g for g in erg["gruppen"] if g["name"] == "Süßwaren & Snacks")
        sonst = next(g for g in erg["gruppen"] if g["name"] == "Sonstiges")
        assert len(suess["angebote"]) == 1 and not suess["angebote"][0]["unsicher"]
        assert len(sonst["angebote"]) == 0
        assert erg["unsicher"] == 0
    finally:
        web._ergebnis_cache.pop(key, None)
