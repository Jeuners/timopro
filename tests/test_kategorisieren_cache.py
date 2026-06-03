"""Cache-Integration in kategorisiere() -- offline, eigene DB pro Test."""

from angebote.kategorisieren import kategorisiere
from angebote.produktcache import ProduktCache
from tests.fakes import CountingFakeKategorisierer, beispiel_angebot


def _cache(tmp_path):
    return ProduktCache(db_pfad=tmp_path / "c.sqlite")


def test_zweiter_lauf_komplett_aus_cache(tmp_path):
    cache = _cache(tmp_path)
    angebote = [
        beispiel_angebot("Butter", marke="Meggle"),
        beispiel_angebot("Apfel", marke=None),
    ]
    # 1. Lauf: alles neu ans LLM, wird gecacht
    fake1 = CountingFakeKategorisierer("Sonstiges", unsicher=False)
    stat1 = {}
    kategorisiere(angebote, fake1, cache=cache, statistik=stat1)
    assert fake1.gesehen == 2
    assert stat1 == {"aus_cache": 0, "neu": 2}

    # 2. Lauf: nichts mehr ans LLM (alles aus Cache)
    fake2 = CountingFakeKategorisierer("Sonstiges")
    stat2 = {}
    erg = kategorisiere(angebote, fake2, cache=cache, statistik=stat2)
    assert fake2.gesehen == 0
    assert stat2 == {"aus_cache": 2, "neu": 0}
    assert all(k.gruppe == "Sonstiges" and not k.unsicher for k in erg)


def test_dedup_ein_produkt_nur_ein_posten(tmp_path):
    cache = _cache(tmp_path)
    # zwei Angebote DESSELBEN Produkts (Titel+Marke), aber versch. Preis/Händler
    a1 = beispiel_angebot("Butter", marke="Meggle", preis=1.49, haendler="REWE")
    a2 = beispiel_angebot("Butter", marke="Meggle", preis=1.99, haendler="EDEKA")
    assert a1.angebot_id != a2.angebot_id
    fake = CountingFakeKategorisierer("Molkereiprodukte & Eier")
    erg = kategorisiere([a1, a2], fake, cache=cache)
    assert fake.gesehen == 1  # nur EIN Posten ans LLM
    assert len(erg) == 2
    assert all(k.gruppe == "Molkereiprodukte & Eier" for k in erg)


def test_unsichere_werden_nicht_gecacht(tmp_path):
    cache = _cache(tmp_path)
    a = beispiel_angebot("Hafer-Pflanzendrink", marke=None)
    fake = CountingFakeKategorisierer("Molkereiprodukte & Eier", unsicher=True)
    kategorisiere([a], fake, cache=cache)
    assert cache.groesse() == 0  # unsicher -> nicht gespeichert
    # Folge-Lauf fragt erneut (keine Propagation des Zweifels)
    fake2 = CountingFakeKategorisierer("Sonstiges")
    kategorisiere([a], fake2, cache=cache)
    assert fake2.gesehen == 1


def test_ohne_cache_geht_alles_ans_llm(tmp_path):
    angebote = [beispiel_angebot("Butter"), beispiel_angebot("Apfel", marke=None)]
    fake = CountingFakeKategorisierer("Sonstiges")
    erg = kategorisiere(angebote, fake)  # cache=None
    assert fake.gesehen == 2
    assert len(erg) == 2
