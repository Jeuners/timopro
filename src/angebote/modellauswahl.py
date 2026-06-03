"""Interaktive Modell-Auswahl für den OpenRouter-Kategorisierer.

Zeigt die aktuell besten Top-5-Free-Modelle, erlaubt Suche und Aktualisieren
und gibt die gewählte Modell-ID zurück. I/O ist injizierbar (`eingabe`/`ausgabe`),
damit der Ablauf ohne TTY testbar ist.

Befehle im Picker:
  [1..N]    Nummer aus der aktuellen Liste wählen
  s TEXT    nach TEXT suchen (über alle Modelle)
  f         zurück zu den Top-5 Free
  u         Liste neu von OpenRouter laden ("Aktualisieren")
  q         abbrechen
"""

from __future__ import annotations

from typing import Callable

from .modelle import ModellInfo, lade_modelle, suche, top_free


def _format(modelle: list[ModellInfo], titel: str) -> str:
    zeilen = [titel]
    for i, m in enumerate(modelle, 1):
        ctx = f"{m.context:,}".replace(",", ".") if m.context else "?"
        frei = "FREE" if m.frei else "paid"
        warn = "" if m.tools else "  ⚠️ KEIN tool-calling (Kategorisierung bliebe leer)"
        zeilen.append(f"  {i}) {m.id}  [{frei}, ctx {ctx}]{warn}")
    if not modelle:
        zeilen.append("  (keine Treffer)")
    return "\n".join(zeilen)


def waehle_modell_interaktiv(
    *,
    session=None,
    eingabe: Callable[[str], str] = input,
    ausgabe: Callable[[str], None] = print,
) -> str | None:
    """Führt den Auswahldialog und gibt die gewählte Modell-ID zurück (oder None)."""
    ausgabe("Lade OpenRouter-Modelle …")
    alle = lade_modelle(session)
    aktuell = top_free(alle, 5)
    titel = "Top-5 Free (tool-fähig, Heuristik – siehe modelle.py):"

    hilfe = (
        "Befehle: [Nummer] wählen · [s TEXT] suchen · [f] Top-5 Free · "
        "[u] aktualisieren · [q] abbrechen"
    )

    while True:
        ausgabe(_format(aktuell, titel))
        ausgabe(hilfe)
        try:
            roh = eingabe("> ").strip()
        except EOFError:
            return None

        if not roh:
            continue
        befehl = roh.lower()

        if befehl in ("q", "quit", "abbrechen"):
            return None

        if befehl in ("u", "update"):
            ausgabe("Aktualisiere …")
            alle = lade_modelle(session)
            aktuell = top_free(alle, 5)
            titel = "Top-5 Free (aktualisiert):"
            continue

        if befehl in ("f", "free"):
            aktuell = top_free(alle, 5)
            titel = "Top-5 Free (tool-fähig, Heuristik):"
            continue

        if befehl.startswith("s ") or befehl == "s":
            begriff = roh[1:].strip()
            aktuell = suche(alle, begriff)[:15]
            titel = f"Suche '{begriff}' (max. 15):"
            continue

        if roh.isdigit():
            idx = int(roh) - 1
            if 0 <= idx < len(aktuell):
                gewaehlt = aktuell[idx]
                if not gewaehlt.tools:
                    ausgabe(
                        "Achtung: Modell kann kein Tool-Calling — die Kategorisierung "
                        "würde leer bleiben. Trotzdem wählen? [j/N]"
                    )
                    if eingabe("> ").strip().lower() not in ("j", "ja", "y"):
                        continue
                ausgabe(f"Gewählt: {gewaehlt.id}")
                return gewaehlt.id
            ausgabe("Nummer außerhalb der Liste.")
            continue

        ausgabe("Eingabe nicht verstanden.")
