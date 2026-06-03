"""Angebots-Übersicht: deterministischer Fetch + LLM-Kategorisierung.

Der Schnitt (siehe CLAUDE.md) ist auch in der Paketstruktur sichtbar:
  * fetch / quellen / modell  -> deterministisch, kein LLM
  * kategorisieren            -> der EINZIGE Ort mit LLM
"""

from .modell import Angebot, FetchErgebnis, KategorisiertesAngebot

__all__ = ["Angebot", "FetchErgebnis", "KategorisiertesAngebot"]
