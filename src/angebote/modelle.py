"""OpenRouter-Modell-Discovery für die Kategorisierer-Auswahl.

Rein deterministisch (KEIN LLM): zieht die Modellliste live von OpenRouter,
erkennt frei nutzbare und tool-fähige Modelle und sortiert sie nach einer
DOKUMENTIERTEN Heuristik.

Ehrlichkeit zu "beste": Die API liefert keine Qualitätsmetrik. "beste" ist hier
deshalb kein Benchmark, sondern eine nachvollziehbare Präferenz bekannter,
starker Modellfamilien -- und IMMER gefiltert auf das, was gerade real
verfügbar UND tool-fähig ist (sonst liefert die Kategorisierung leer).
"""

from __future__ import annotations

from dataclasses import dataclass

MODELS_URL = "https://openrouter.ai/api/v1/models"

# Dokumentierte Präferenz (Meinung, kein Benchmark). Reihenfolge = Rang.
# Modelle, die hier matchen, gelten als "stärker"; der Rest folgt nach
# Kontextgröße. Bei Bedarf hier anpassen -- die Liste lebt in der Config-Ebene,
# nicht in der Logik.
PRAEFERENZ: tuple[str, ...] = (
    "kimi-k2",
    "qwen3-next",
    "llama-3.3-70b",
    "gpt-oss-120b",
    "glm-4.5",
    "qwen3-coder",
    "nemotron-3-super",
    "gemma-4-31b",
    "qwen3",
    "llama",
    "gemma",
    "nemotron",
    "gpt-oss",
    "mistral",
)


@dataclass(frozen=True)
class ModellInfo:
    id: str
    name: str
    context: int | None
    frei: bool
    tools: bool


def _als_float(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 1.0  # unbekannt -> als "nicht frei" werten, nicht raten


def parse_modelle(daten: list[dict]) -> list[ModellInfo]:
    out: list[ModellInfo] = []
    for m in daten:
        p = m.get("pricing") or {}
        frei = _als_float(p.get("prompt")) == 0 and _als_float(p.get("completion")) == 0
        params = m.get("supported_parameters") or []
        out.append(
            ModellInfo(
                id=m.get("id", ""),
                name=m.get("name") or m.get("id", ""),
                context=m.get("context_length"),
                frei=frei,
                tools="tools" in params,
            )
        )
    return out


def lade_modelle(session=None) -> list[ModellInfo]:
    """Zieht die Modellliste live (= 'aktualisieren'). Kein Key nötig."""
    sess = session
    if sess is None:
        import requests

        sess = requests
    antwort = sess.get(MODELS_URL, timeout=30)
    antwort.raise_for_status()
    return parse_modelle(antwort.json().get("data", []))


def _rang(mi: ModellInfo) -> tuple:
    low = mi.id.lower()
    for i, schluessel in enumerate(PRAEFERENZ):
        if schluessel in low:
            return (0, i, -(mi.context or 0))
    return (1, 0, -(mi.context or 0))


def top_free(modelle: list[ModellInfo], n: int = 5, nur_tools: bool = True) -> list[ModellInfo]:
    """Die n besten frei nutzbaren Modelle (standardmäßig nur tool-fähige)."""
    kandidaten = [m for m in modelle if m.frei and (m.tools or not nur_tools)]
    return sorted(kandidaten, key=_rang)[:n]


def suche(
    modelle: list[ModellInfo],
    begriff: str,
    *,
    nur_frei: bool = False,
    nur_tools: bool = False,
) -> list[ModellInfo]:
    """Filtert nach Teilstring in id/name; optional auf frei/tool-fähig."""
    b = (begriff or "").lower().strip()
    res = [m for m in modelle if b in m.id.lower() or b in m.name.lower()]
    if nur_frei:
        res = [m for m in res if m.frei]
    if nur_tools:
        res = [m for m in res if m.tools]
    return sorted(res, key=_rang)
