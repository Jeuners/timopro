"""Tests für den Produkt→Kategorie-Cache -- offline, eigene DB pro Test."""

import subprocess
import sys
from pathlib import Path

from angebote.produktcache import ProduktCache, produkt_schluessel

SRC = Path(__file__).resolve().parents[1] / "src"


def _cache(tmp_path) -> ProduktCache:
    return ProduktCache(db_pfad=tmp_path / "cache.sqlite")


# -- Schlüssel ----------------------------------------------------------------


def test_schluessel_ist_mengen_invariant():
    # Titel + Marke bestimmen den Schlüssel; Menge spielt keine Rolle.
    assert produkt_schluessel("Butter", "Meggle") == produkt_schluessel(
        " butter ", "MEGGLE"
    )


def test_schluessel_unterscheidet_marke():
    assert produkt_schluessel("Butter", "Meggle") != produkt_schluessel(
        "Butter", "Kerrygold"
    )


# -- Round-Trip / Persistenz --------------------------------------------------


def test_round_trip_ueber_instanzgrenzen(tmp_path):
    db = tmp_path / "c.sqlite"
    c1 = ProduktCache(db_pfad=db)
    s = produkt_schluessel("Toffifee", "Storck")
    c1.schreibe_viele([(s, "Süßwaren & Snacks", "deepseek")])
    # frische Instanz auf derselben DB
    c2 = ProduktCache(db_pfad=db)
    assert c2.hole(s) == "Süßwaren & Snacks"
    assert c2.groesse() == 1


def test_unbekannter_schluessel_gibt_none(tmp_path):
    c = _cache(tmp_path)
    assert c.hole("gibtsnicht") is None


# -- Geschlossene Liste (Whitelist) ------------------------------------------


def test_off_list_gruppe_wird_nicht_geschrieben(tmp_path):
    c = _cache(tmp_path)
    n = c.schreibe_viele([("k1", "Weltraumzeug", None)])
    assert n == 0
    assert c.hole("k1") is None


def test_off_list_zeile_in_db_wird_beim_lesen_verworfen(tmp_path):
    import sqlite3

    db = tmp_path / "c.sqlite"
    ProduktCache(db_pfad=db)  # legt Tabelle an
    # manipulierte Zeile direkt in die DB schreiben
    with sqlite3.connect(str(db)) as con:
        con.execute(
            "INSERT INTO produkt_kategorie VALUES (?,?,?,?)",
            ("k1", "Quatschgruppe", None, "2026-01-01"),
        )
    c = ProduktCache(db_pfad=db)
    assert c.hole("k1") is None  # Whitelist filtert sie heraus
    assert c.groesse() == 0


# -- Schnitt: kein LLM im Cache ----------------------------------------------


def test_cache_laedt_kein_anthropic():
    code = (
        "import sys; import angebote.produktcache; "
        "assert 'anthropic' not in sys.modules, 'Cache hat anthropic geladen'; "
        "print('ok')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=str(SRC), capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout


def test_cache_importiert_kein_llm():
    quelltext = (SRC / "angebote" / "produktcache.py").read_text("utf-8")
    import_zeilen = "\n".join(
        z for z in quelltext.splitlines()
        if z.strip().startswith(("import ", "from "))
    ).lower()
    assert "anthropic" not in import_zeilen
    assert "openai" not in import_zeilen
    assert "kategorisieren" not in import_zeilen
