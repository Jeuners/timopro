"""Adapter-Schnittstelle für Quellen.

Vertrag: rein = `Ort`, raus = `list[Angebot]`. Jeder Adapter kapselt genau eine
Quelle; die Kernlogik (fetch.py) kennt nur diese Schnittstelle, nicht die
einzelne Quelle. So lassen sich Quellen austauschen, ohne den Kern anzufassen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..modell import Angebot


@dataclass(frozen=True)
class Ort:
    """Aufgelöster Ort. `plz` ist Pflicht -- ein Adapter filtert darüber."""

    plz: str
    name: str | None = None


@runtime_checkable
class QuelleAdapter(Protocol):
    """Eine Angebotsquelle.

    `name`        -- Anzeigename der Quelle.
    `deckt_ab`    -- ob die Quelle den Ort bedienen kann (entscheidet mit über
                     Regel 4: deckt KEINE Quelle den Ort ab -> Abbruch).
    `hole`        -- liefert belegte Angebote für den Ort. Liefert die Quelle
                     nichts, ist das ein leeres Ergebnis -- KEIN Auffüllen.
                     Kann die Quelle den Ortsbezug nicht verifizieren oder den
                     nötigen Zugang nicht herstellen, wirft sie AbbruchFehler.
    """

    name: str

    def deckt_ab(self, ort: Ort) -> bool: ...

    def hole(self, ort: Ort) -> list[Angebot]: ...
