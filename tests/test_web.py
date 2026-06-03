"""Web-Schicht -- offline. Struktur-Funktion + Endpoints (ohne Netz/Key/LLM).

Der Schnitt gilt auch hier und ist im Endpoint-Schnitt sichtbar:
  * Stufe 1 (/api/rohdaten) holt + speichert deterministisch -- ohne Key.
  * Stufe 2 (/api/kategorisieren) ist gesperrt, solange keine Rohdaten vorliegen.

Geprüft wird, dass die Web-Schicht das belegt-und-ehrlich weiterreicht und die
zwei Stufen sauber trennt -- ohne dabei selbst zu fetchen oder ein LLM zu rufen.
"""

import pytest

from angebote.modell import FetchErgebnis, KategorisiertesAngebot
from angebote.uebersicht import als_struktur
from tests.fakes import FakeQuelle, beispiel_angebot

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


def test_api_status_unbekannt_ist_404():
    client = TestClient(web.app)
    r = client.get("/api/lauf/gibtsnicht")
    assert r.status_code == 404


def test_als_struktur_fuehrt_modell_und_anbieter():
    a = beispiel_angebot("Butter")
    kat = [KategorisiertesAngebot(a, "Molkereiprodukte & Eier", unsicher=False)]
    s = als_struktur(_fetch_mit([a]), kat, modell="qwen3.5:latest", anbieter="ollama")
    assert s["modell"] == "qwen3.5:latest"
    assert s["anbieter"] == "ollama"


def test_api_ollama_modelle(monkeypatch):
    fake = [ModellInfo("qwen3.5:latest", "qwen3.5:latest", None, True, True)]
    monkeypatch.setattr(
        "angebote.modelle.lade_ollama_modelle", lambda session=None: fake
    )
    client = TestClient(web.app)
    r = client.get("/api/ollama-modelle")
    assert r.status_code == 200
    daten = r.json()
    assert daten[0]["id"] == "qwen3.5:latest" and daten[0]["tools"] is True


# === Stufe 1: Rohdaten holen & speichern (deterministisch, ohne Key) =========


def test_api_rohdaten_ohne_plz_ist_400():
    client = TestClient(web.app)
    r = client.post("/api/rohdaten", json={"plz": ""})
    assert r.status_code == 400


def test_api_rohdaten_holen_speichert_und_laedt(tmp_path, monkeypatch):
    """Stufe 1 fetcht (über Fake-Quelle, kein Netz), speichert, und GET liefert es."""
    # Persistenz in tmp lenken -- der Default-Pfad bleibt unangetastet.
    monkeypatch.setattr("angebote.speicher.STANDARD_BASIS", tmp_path / "roh")
    # Fetch über eine Fake-Quelle: kein Netz, kein Schlüssel, deterministisch.
    a = beispiel_angebot("Bio-Banane", haendler="ALDI SÜD", preis=1.29)
    quelle = FakeQuelle("fake", [a])
    monkeypatch.setattr("angebote.fetch.standard_quellen", lambda: [quelle])

    client = TestClient(web.app)
    r = client.post("/api/rohdaten", json={"plz": "60487"})
    assert r.status_code == 200
    d = r.json()
    assert d["plz"] == "60487"
    assert d["anzahl"] == 1
    assert "ALDI SÜD" in d["haendler"]
    assert d["angebote"][0]["titel"] == "Bio-Banane"
    assert d["abgerufen_am"]  # belegt

    # Datei wurde geschrieben (data/roh-Äquivalent im tmp)
    geschrieben = list((tmp_path / "roh").glob("60487_*.json"))
    assert geschrieben, "Rohdaten-Datei wurde nicht persistiert"

    # GET liefert den gespeicherten Stand zurück (kein erneutes Fetchen nötig).
    g = client.get("/api/rohdaten/60487")
    assert g.status_code == 200
    assert g.json()["angebote"][0]["titel"] == "Bio-Banane"


def test_api_rohdaten_holen_abbruch_ist_422(monkeypatch, tmp_path):
    """Ehrlicher Abbruch (Regel 4) wird als 422 mit Ursache/Vorschlag gemeldet."""
    monkeypatch.setattr("angebote.speicher.STANDARD_BASIS", tmp_path / "roh")
    # Keine Quelle deckt den Ort ab -> AbbruchFehler.
    quelle = FakeQuelle("fake", [], deckt=False)
    monkeypatch.setattr("angebote.fetch.standard_quellen", lambda: [quelle])

    client = TestClient(web.app)
    r = client.post("/api/rohdaten", json={"plz": "60487"})
    assert r.status_code == 422
    assert "Abbruch" in r.json()["detail"]


def test_api_rohdaten_laden_ohne_stand_ist_404(monkeypatch, tmp_path):
    monkeypatch.setattr("angebote.speicher.STANDARD_BASIS", tmp_path / "roh")
    client = TestClient(web.app)
    r = client.get("/api/rohdaten/99999")
    assert r.status_code == 404


# === Stufe 2: Kategorisieren -- gesperrt ohne Rohdaten =======================


def test_api_kategorisieren_ohne_rohdaten_ist_400(monkeypatch, tmp_path):
    """Stufe 2 ist hart gesperrt, solange keine Rohdaten gespeichert sind."""
    monkeypatch.setattr("angebote.speicher.STANDARD_BASIS", tmp_path / "roh")
    client = TestClient(web.app)
    r = client.post("/api/kategorisieren", json={"plz": "60487"})
    assert r.status_code == 400
    assert "Rohdaten" in r.json()["detail"]


def test_api_kategorisieren_ohne_plz_ist_400():
    client = TestClient(web.app)
    r = client.post("/api/kategorisieren", json={"plz": ""})
    assert r.status_code == 400
