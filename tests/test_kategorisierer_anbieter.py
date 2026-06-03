"""Anbieter-Factory + OpenRouter-Antwortform -- offline, ohne Netz/Key."""

import json

import pytest

from angebote.fehler import AbbruchFehler
from angebote.kategorisieren import (
    OpenRouterKategorisierer,
    baue_kategorisierer,
    kategorisiere,
)
from tests.fakes import beispiel_angebot


class _FakeResp:
    def __init__(self, payload, status_code=200):
        self._p = payload
        self.status_code = status_code
        self.headers = {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class _FakeSession:
    def __init__(self, payload):
        self._p = payload
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResp(self._p)


def _openrouter_payload(zuordnungen):
    return {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "zuordnungen",
                                "arguments": json.dumps({"zuordnungen": zuordnungen}),
                            }
                        }
                    ]
                }
            }
        ]
    }


def test_factory_unbekannter_anbieter_bricht_ab():
    with pytest.raises(AbbruchFehler):
        baue_kategorisierer("gibtsnicht")


def test_factory_openrouter_ohne_key_bricht_ehrlich_ab(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(AbbruchFehler) as exc:
        baue_kategorisierer("openrouter")
    assert "OPENROUTER_API_KEY" in exc.value.ursache


def test_openrouter_parst_openai_tool_calls():
    angebote = [beispiel_angebot("Apfel"), beispiel_angebot("Bohrmaschine")]
    payload = _openrouter_payload(
        [
            {"id": angebote[0].angebot_id, "gruppe": "Obst & Gemüse", "unsicher": False},
            {
                "id": angebote[1].angebot_id,
                "gruppe": "Non-Food (Kleidung, Spielzeug, Garten, Technik)",
                "unsicher": False,
            },
        ]
    )
    sess = _FakeSession(payload)
    kat = OpenRouterKategorisierer(api_key="test-key", session=sess)
    ergebnis = kategorisiere(angebote, kat)

    gruppen = {k.angebot.titel: k.gruppe for k in ergebnis}
    assert gruppen["Apfel"] == "Obst & Gemüse"
    assert gruppen["Bohrmaschine"].startswith("Non-Food")
    # Request war OpenAI-kompatibel adressiert und authentifiziert:
    aufruf = sess.calls[0]
    assert aufruf["url"].endswith("/chat/completions")
    assert aufruf["json"]["tool_choice"]["function"]["name"] == "zuordnungen"
    assert aufruf["headers"]["Authorization"] == "Bearer test-key"


def test_openrouter_api_fehler_bricht_ab():
    sess = _FakeSession({"error": {"message": "insufficient_credits"}})
    kat = OpenRouterKategorisierer(api_key="test-key", session=sess)
    with pytest.raises(AbbruchFehler):
        kat.klassifiziere([{"id": "x", "titel": "Apfel"}])


class _SeqSession:
    """Liefert eine Folge vorgegebener Antworten (für Retry-Tests)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def post(self, url, json=None, headers=None, timeout=None):
        r = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return r


def test_openrouter_retry_bei_429_dann_erfolg():
    payload = _openrouter_payload(
        [{"id": "x", "gruppe": "Sonstiges", "unsicher": False}]
    )
    seq = _SeqSession(
        [_FakeResp({}, 429), _FakeResp({}, 429), _FakeResp(payload, 200)]
    )
    geschlafen = []
    kat = OpenRouterKategorisierer(
        api_key="k",
        session=seq,
        mindest_abstand_s=0.0,
        schlafen=geschlafen.append,
    )
    res = kat.klassifiziere([{"id": "x", "titel": "Apfel"}])
    assert res == [{"id": "x", "gruppe": "Sonstiges", "unsicher": False}]
    assert seq.calls == 3
    assert len(geschlafen) == 2  # zwei Backoffs vor dem Erfolg, kein echtes Warten


def test_openrouter_429_erschoepft_bricht_als_ratelimit_ab():
    seq = _SeqSession([_FakeResp({}, 429)])
    kat = OpenRouterKategorisierer(
        api_key="k", session=seq, max_versuche=3, mindest_abstand_s=0.0, schlafen=lambda s: None
    )
    with pytest.raises(AbbruchFehler) as exc:
        kat.klassifiziere([{"id": "x", "titel": "Apfel"}])
    assert "Rate-Limit" in exc.value.schwelle
    assert seq.calls == 3


def test_baue_kategorisierer_ollama_ohne_key():
    from angebote.kategorisieren import OllamaKategorisierer, baue_kategorisierer

    # Ollama braucht KEINEN Key -- darf also nicht abbrechen.
    kt = baue_kategorisierer("ollama", "qwen3.5:latest")
    assert isinstance(kt, OllamaKategorisierer)


def test_ollama_kategorisierer_parst_tool_calls_lokal():
    from angebote.kategorisieren import OllamaKategorisierer

    a = beispiel_angebot("Apfel")
    payload = _openrouter_payload(
        [{"id": a.angebot_id, "gruppe": "Obst & Gemüse", "unsicher": False}]
    )
    sess = _FakeSession(payload)
    kt = OllamaKategorisierer(modell="qwen3.5:latest", session=sess)
    ergebnis = kategorisiere([a], kt)
    assert ergebnis[0].gruppe == "Obst & Gemüse"
    # OpenAI-kompatibel an den lokalen Endpoint adressiert:
    assert sess.calls[0]["url"].endswith("/chat/completions")
    assert "localhost:11434" in sess.calls[0]["url"]