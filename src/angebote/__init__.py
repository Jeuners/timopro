"""Angebots-Übersicht: deterministischer Fetch + LLM-Kategorisierung.

Der Schnitt (siehe CLAUDE.md) ist auch in der Paketstruktur sichtbar:
  * fetch / quellen / modell  -> deterministisch, kein LLM
  * kategorisieren            -> der EINZIGE Ort mit LLM
"""

from .modell import Angebot, FetchErgebnis, KategorisiertesAngebot

__version__ = "0.1.0"

__all__ = ["Angebot", "FetchErgebnis", "KategorisiertesAngebot", "__version__"]
