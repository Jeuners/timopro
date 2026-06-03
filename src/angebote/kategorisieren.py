"""Kategorisier-Teil -- der EINZIGE Ort mit LLM.

Aufbau bewusst so, dass die harten Regeln im *Code* erzwungen werden, nicht im
Prompt erbeten:

  * Dem Modell wird pro Posten nur {id, titel, marke, menge} gezeigt -- nie
    Preis/Gültigkeit/Händler. Es kann sie also gar nicht "korrigieren".
  * Vom Modell übernommen werden NUR `gruppe` + `unsicher`. Das Original-Angebot
    bleibt unverändert (es ist ohnehin frozen).
  * Eine Gruppe außerhalb der geschlossenen Liste wird NICHT übernommen ->
    Fallback-Gruppe + `unsicher=True`.
  * Ein Posten, den das Modell gar nicht beantwortet, wird `unsicher` mit
    Fallback-Gruppe -- nicht still einsortiert.

Das LLM steckt hinter `Kategorisierer`; Tests reichen einen Fake herein und
laufen damit ohne Netz und ohne Schlüssel.
"""

from __future__ import annotations

import json
import os
from typing import Protocol

from .config import FALLBACK_GRUPPE, PRODUKTGRUPPEN
from .fehler import AbbruchFehler
from .modell import Angebot, KategorisiertesAngebot


class Kategorisierer(Protocol):
    """Bekommt Posten [{id, titel, marke, menge}], gibt [{id, gruppe, unsicher}]."""

    def klassifiziere(self, posten: list[dict]) -> list[dict]: ...


def kategorisiere(
    angebote: list[Angebot],
    kategorisierer: Kategorisierer,
    *,
    batch_groesse: int = 25,
    fortschritt=None,
) -> list[KategorisiertesAngebot]:
    """Ordnet jedes Angebot einer Produktgruppe zu, ohne Daten zu verändern.

    `fortschritt`: optionaler Callback (erledigte_batches, gesamt_batches) --
    für Live-Anzeigen (z. B. die Web-UI). Ändert die Logik nicht.
    """
    original = {a.angebot_id: a for a in angebote}
    ergebnis: dict[str, KategorisiertesAngebot] = {}

    import math

    gesamt_batches = max(1, math.ceil(len(angebote) / batch_groesse))
    for nr, start in enumerate(range(0, len(angebote), batch_groesse), 1):
        batch = angebote[start : start + batch_groesse]
        posten = [
            {
                "id": a.angebot_id,
                "titel": a.titel,
                "marke": a.marke,
                "menge": a.menge,
            }
            for a in batch
        ]
        antworten = kategorisierer.klassifiziere(posten)
        for ant in antworten:
            aid = ant.get("id")
            if aid not in original or aid in ergebnis:
                continue  # fremde/duplizierte ID ignorieren
            gruppe, unsicher = _bereinige_gruppe(ant.get("gruppe"), ant.get("unsicher"))
            ergebnis[aid] = KategorisiertesAngebot(
                angebot=original[aid], gruppe=gruppe, unsicher=unsicher
            )
        if fortschritt is not None:
            fortschritt(nr, gesamt_batches)

    # Posten, die das Modell nicht (gültig) beantwortet hat: ehrlich als
    # unsicher mit Fallback markieren -- nicht still einsortieren.
    out: list[KategorisiertesAngebot] = []
    for a in angebote:
        out.append(
            ergebnis.get(
                a.angebot_id,
                KategorisiertesAngebot(angebot=a, gruppe=FALLBACK_GRUPPE, unsicher=True),
            )
        )
    return out


def _bereinige_gruppe(gruppe, unsicher) -> tuple[str, bool]:
    """Erzwingt die geschlossene Liste. Off-list -> Fallback + unsicher."""
    flag = bool(unsicher)
    if isinstance(gruppe, str) and gruppe in PRODUKTGRUPPEN:
        return gruppe, flag
    return FALLBACK_GRUPPE, True


# --- echte LLM-Implementierung ----------------------------------------------

_SYSTEM = (
    "Du ordnest Supermarkt-Angebote genau EINER Produktgruppe aus einer "
    "geschlossenen Liste zu. Erfinde keine neuen Gruppen. Wähle ausschließlich "
    "aus dieser Liste:\n- "
    + "\n- ".join(PRODUKTGRUPPEN)
    + "\n\nPasst ein Artikel in keine, nimm 'Sonstiges'. Wenn du dir unsicher "
    "bist, setze unsicher=true und gib die wahrscheinlichste Gruppe an -- rate "
    "nicht still. Verändere keine Produktnamen. Antworte für JEDEN übergebenen "
    "Posten genau einmal über das Tool, identifiziert durch seine id."
)

_TOOL = {
    "name": "zuordnungen",
    "description": "Gibt für jeden Posten die Produktgruppe und ein Unsicherheits-Flag zurück.",
    "input_schema": {
        "type": "object",
        "properties": {
            "zuordnungen": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "gruppe": {"type": "string", "enum": list(PRODUKTGRUPPEN)},
                        "unsicher": {"type": "boolean"},
                    },
                    "required": ["id", "gruppe", "unsicher"],
                },
            }
        },
        "required": ["zuordnungen"],
    },
}


def _user_text(posten: list[dict]) -> str:
    return "Ordne diese Posten zu:\n" + "\n".join(
        f"- id={p['id']} | titel={p['titel']} | "
        f"marke={p.get('marke')} | menge={p.get('menge')}"
        for p in posten
    )


def _wartezeit(antwort, versuch: int, basis: float) -> float:
    """Backoff: Retry-After respektieren, sonst exponentiell ab max(basis, 2s)."""
    try:
        ra = antwort.headers.get("Retry-After")
    except Exception:
        ra = None
    if ra:
        try:
            return float(ra)
        except (TypeError, ValueError):
            pass
    grund = basis if basis > 0 else 2.0
    return grund * (2**versuch)


class AnthropicKategorisierer:
    """Kategorisierer auf Basis der nativen Anthropic-API (Tool-Use)."""

    def __init__(self, *, client=None, modell: str = "claude-sonnet-4-6") -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()  # liest ANTHROPIC_API_KEY aus der Umgebung
        self._client = client
        self._modell = modell

    def klassifiziere(self, posten: list[dict]) -> list[dict]:
        nachricht = self._client.messages.create(
            model=self._modell,
            max_tokens=2048,
            system=[
                {"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}
            ],
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "zuordnungen"},
            messages=[{"role": "user", "content": _user_text(posten)}],
        )
        for block in nachricht.content:
            if getattr(block, "type", None) == "tool_use":
                return list(block.input.get("zuordnungen", []))
        return []


class OpenRouterKategorisierer:
    """Kategorisierer über OpenRouter (OpenAI-kompatibles Tool-Calling).

    Nutzt nur `requests` -- kein anbieterspezifisches SDK. Liest den Zugang aus
    OPENROUTER_API_KEY. Modell-IDs im OpenRouter-Namespace, z. B.
    'anthropic/claude-sonnet-4.6'. Bei Transport-/Antwortfehlern: ehrlicher
    AbbruchFehler statt stiller Drift.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        modell: str = "anthropic/claude-sonnet-4.6",
        base_url: str = "https://openrouter.ai/api/v1",
        session=None,
        max_versuche: int = 5,
        mindest_abstand_s: float | None = None,
        schlafen=None,
    ) -> None:
        self._key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self._key:
            raise AbbruchFehler(
                schwelle="openrouter: Zugang",
                ursache="OPENROUTER_API_KEY ist nicht gesetzt",
                vorschlag="Key setzen ODER --no-llm für die belegte Rohliste verwenden",
            )
        self._modell = modell
        self._base = base_url.rstrip("/")
        self._session = session
        self._max = max(1, max_versuche)
        # Free-Modelle drosseln hart (~20/min). Endet die ID auf ':free' und ist
        # kein Abstand vorgegeben, throttlen wir automatisch auf ~20/min.
        if mindest_abstand_s is None:
            mindest_abstand_s = 3.2 if modell.endswith(":free") else 0.0
        self._abstand = mindest_abstand_s
        self._letzter = 0.0
        # injizierbar für Tests (kein echtes Warten):
        if schlafen is None:
            import time

            schlafen = time.sleep
        self._schlafen = schlafen

    def _sess(self):
        if self._session is None:
            import requests

            self._session = requests.Session()
        return self._session

    def _throttle(self) -> None:
        if self._abstand <= 0:
            return
        import time

        seit = time.monotonic() - self._letzter
        if 0 < seit < self._abstand:
            self._schlafen(self._abstand - seit)
        self._letzter = time.monotonic()

    def klassifiziere(self, posten: list[dict]) -> list[dict]:
        tool = {
            "type": "function",
            "function": {
                "name": _TOOL["name"],
                "description": _TOOL["description"],
                "parameters": _TOOL["input_schema"],
            },
        }
        payload = {
            "model": self._modell,
            "max_tokens": 2048,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _user_text(posten)},
            ],
            "tools": [tool],
            "tool_choice": {"type": "function", "function": {"name": _TOOL["name"]}},
        }
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "X-Title": "angebote-uebersicht",
        }

        daten = None
        for versuch in range(self._max):
            self._throttle()
            try:
                antwort = self._sess().post(
                    f"{self._base}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=60,
                )
            except Exception as e:
                if versuch + 1 < self._max:
                    self._schlafen(self._abstand or 2.0)
                    continue
                raise AbbruchFehler(
                    schwelle="openrouter: Kategorisierung",
                    ursache=f"chat/completions nicht erreichbar ({e})",
                    vorschlag="Netz prüfen oder --no-llm verwenden",
                ) from e

            status = getattr(antwort, "status_code", 200)
            # 429 (Rate-Limit) / 5xx -> mit Backoff erneut versuchen.
            if status == 429 or status >= 500:
                if versuch + 1 < self._max:
                    self._schlafen(_wartezeit(antwort, versuch, self._abstand))
                    continue
                raise AbbruchFehler(
                    schwelle="openrouter: Rate-Limit",
                    ursache=f"HTTP {status} auch nach {self._max} Versuchen "
                    "(Free-Modell zu stark gedrosselt?)",
                    vorschlag="bezahltes Modell wählen, später erneut, oder --no-llm",
                )
            try:
                antwort.raise_for_status()
                daten = antwort.json()
            except Exception as e:
                raise AbbruchFehler(
                    schwelle="openrouter: Kategorisierung",
                    ursache=f"chat/completions fehlgeschlagen ({e})",
                    vorschlag="Key/Modell/Guthaben prüfen oder --no-llm verwenden",
                ) from e
            break

        if isinstance(daten, dict) and daten.get("error"):
            raise AbbruchFehler(
                schwelle="openrouter: Kategorisierung",
                ursache=f"API-Fehler: {daten['error']}",
                vorschlag="Key/Modell/Guthaben prüfen oder --no-llm verwenden",
            )
        try:
            aufrufe = daten["choices"][0]["message"]["tool_calls"]
            args = json.loads(aufrufe[0]["function"]["arguments"])
            return list(args.get("zuordnungen", []))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            # Modell hat das Tool nicht (sauber) aufgerufen -> leer; die
            # kategorisiere()-Logik markiert die Posten dann als unsicher.
            return []


_DEFAULT_MODELLE = {
    "anthropic": "claude-sonnet-4-6",
    "openrouter": "anthropic/claude-sonnet-4.6",
}


def baue_kategorisierer(
    anbieter: str, modell: str | None = None, *, api_key: str | None = None
) -> Kategorisierer:
    """Factory: wählt die LLM-Implementierung hinter dem gleichen Protokoll.

    `api_key` optional -- ohne wird er aus der Umgebung gelesen (CLI-Fall);
    mitgegeben für die Web-UI, falls der Key nicht in der Server-Env steht.
    """
    modell = modell or _DEFAULT_MODELLE.get(anbieter)
    if anbieter == "openrouter":
        return OpenRouterKategorisierer(modell=modell, api_key=api_key)
    if anbieter == "anthropic":
        return AnthropicKategorisierer(modell=modell)
    raise AbbruchFehler(
        schwelle="LLM-Anbieter",
        ursache=f"unbekannter Anbieter '{anbieter}'",
        vorschlag="openrouter oder anthropic wählen",
    )
