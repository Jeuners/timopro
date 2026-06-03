"""Fehler, die den Abbruch statt stiller Drift erzwingen.

`AbbruchFehler` ist Regel 4 in Codeform: Schwelle, Ursache und ein konkreter
Vorschlag werden mitgeführt, damit der Abbruch ein *brauchbares* Ergebnis ist --
nicht nur ein Stacktrace.
"""

from __future__ import annotations


class AbbruchFehler(Exception):
    """Die Datenlage trägt die Anforderung nicht -- bewusster, belegter Abbruch."""

    def __init__(self, schwelle: str, ursache: str, vorschlag: str) -> None:
        self.schwelle = schwelle
        self.ursache = ursache
        self.vorschlag = vorschlag
        super().__init__(f"{schwelle}: {ursache} -- Vorschlag: {vorschlag}")

    def als_text(self) -> str:
        return (
            f"Abbruch ({self.schwelle}).\n"
            f"  Ursache:   {self.ursache}\n"
            f"  Vorschlag: {self.vorschlag}"
        )
