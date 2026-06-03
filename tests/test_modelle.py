"""Modell-Discovery + interaktive Auswahl -- offline, ohne Netz/Key."""

from angebote.modelle import lade_modelle, parse_modelle, suche, top_free
from angebote.modellauswahl import waehle_modell_interaktiv

FAKE = [
    {
        "id": "moonshotai/kimi-k2.6:free",
        "name": "Kimi K2",
        "context_length": 262144,
        "pricing": {"prompt": "0", "completion": "0"},
        "supported_parameters": ["tools", "response_format"],
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct:free",
        "name": "Llama 3.3 70B",
        "context_length": 131072,
        "pricing": {"prompt": "0", "completion": "0"},
        "supported_parameters": ["tools"],
    },
    {
        "id": "some/free-no-tools:free",
        "name": "Free ohne Tools",
        "context_length": 100000,
        "pricing": {"prompt": "0", "completion": "0"},
        "supported_parameters": [],
    },
    {
        "id": "anthropic/claude-sonnet-4.6",
        "name": "Claude Sonnet 4.6",
        "context_length": 200000,
        "pricing": {"prompt": "3", "completion": "15"},
        "supported_parameters": ["tools"],
    },
]


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class _Session:
    def __init__(self, data):
        self._data = data

    def get(self, url, timeout=None):
        return _Resp({"data": self._data})


def _scripted(antworten):
    it = iter(antworten)
    return lambda prompt="": next(it)


# --- reine Daten-Logik -------------------------------------------------------


def test_parse_erkennt_frei_und_tools():
    modelle = parse_modelle(FAKE)
    nach_id = {m.id: m for m in modelle}
    assert nach_id["moonshotai/kimi-k2.6:free"].frei is True
    assert nach_id["moonshotai/kimi-k2.6:free"].tools is True
    assert nach_id["anthropic/claude-sonnet-4.6"].frei is False
    assert nach_id["some/free-no-tools:free"].tools is False


def test_top_free_nur_tools_und_rangfolge():
    modelle = parse_modelle(FAKE)
    top = top_free(modelle, 5, nur_tools=True)
    ids = [m.id for m in top]
    # paid (Sonnet) und das tool-lose Free-Modell sind raus:
    assert "anthropic/claude-sonnet-4.6" not in ids
    assert "some/free-no-tools:free" not in ids
    # Präferenz: kimi-k2 vor llama-3.3-70b
    assert ids == [
        "moonshotai/kimi-k2.6:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ]


def test_suche_findet_teilstring():
    modelle = parse_modelle(FAKE)
    treffer = suche(modelle, "llama")
    assert [m.id for m in treffer] == ["meta-llama/llama-3.3-70b-instruct:free"]


def test_lade_modelle_ueber_session():
    modelle = lade_modelle(session=_Session(FAKE))
    assert len(modelle) == 4


# --- interaktiver Picker -----------------------------------------------------


def test_picker_waehlt_per_nummer():
    gewaehlt = waehle_modell_interaktiv(
        session=_Session(FAKE),
        eingabe=_scripted(["1"]),
        ausgabe=lambda s: None,
    )
    assert gewaehlt == "moonshotai/kimi-k2.6:free"


def test_picker_suche_dann_wahl():
    gewaehlt = waehle_modell_interaktiv(
        session=_Session(FAKE),
        eingabe=_scripted(["s llama", "1"]),
        ausgabe=lambda s: None,
    )
    assert gewaehlt == "meta-llama/llama-3.3-70b-instruct:free"


def test_picker_warnt_bei_modell_ohne_tools_und_bricht_ab():
    # Suche bringt das tool-lose Modell in die Liste; Wahl -> Warnung -> 'n' -> q.
    gewaehlt = waehle_modell_interaktiv(
        session=_Session(FAKE),
        eingabe=_scripted(["s no-tools", "1", "n", "q"]),
        ausgabe=lambda s: None,
    )
    assert gewaehlt is None


def test_picker_quit_gibt_none():
    gewaehlt = waehle_modell_interaktiv(
        session=_Session(FAKE),
        eingabe=_scripted(["q"]),
        ausgabe=lambda s: None,
    )
    assert gewaehlt is None
