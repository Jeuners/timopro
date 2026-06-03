"""Gruppierung + Rendering der fertigen Übersicht.

Regeln, die auch hier sichtbar bleiben:
  * Reihenfolge = feste Produktgruppen-Liste (config), nicht "nach Häufigkeit".
  * Leere Gruppen werden als "keine Angebote" gezeigt -- nicht weggelassen,
    nicht aufgefüllt.
  * Unsicher zugeordnete Artikel sind markiert (Mensch kann nachsehen).
  * Bekannte Abdeckungslücken (z. B. Aldi/Lidl) werden ehrlich genannt.
"""

from __future__ import annotations

from .config import PRODUKTGRUPPEN
from .modell import FetchErgebnis, KategorisiertesAngebot


def gruppieren(
    kategorisiert: list[KategorisiertesAngebot],
) -> dict[str, list[KategorisiertesAngebot]]:
    """Gruppiert in der festen Reihenfolge der Produktgruppen-Config."""
    gruppen: dict[str, list[KategorisiertesAngebot]] = {g: [] for g in PRODUKTGRUPPEN}
    for ka in kategorisiert:
        # _bereinige_gruppe garantiert: ka.gruppe ist in PRODUKTGRUPPEN.
        gruppen[ka.gruppe].append(ka)
    return gruppen


def _angebot_dict(ka: KategorisiertesAngebot) -> dict:
    a = ka.angebot
    return {
        "titel": a.titel,
        "marke": a.marke,
        "preis": a.preis,
        "grundpreis": a.grundpreis,
        "menge": a.menge,
        "haendler": a.haendler,
        "gueltig_von": a.gueltig_von.isoformat() if a.gueltig_von else None,
        "gueltig_bis": a.gueltig_bis.isoformat() if a.gueltig_bis else None,
        "quelle": a.quelle,
        "unsicher": ka.unsicher,
    }


def als_struktur(
    fetch: FetchErgebnis,
    kategorisiert: list[KategorisiertesAngebot],
) -> dict:
    """Strukturierte Ausgabe für die Web-UI -- dieselben belegten Felder wie der
    Markdown-Renderer, nur als JSON-fähiges dict. Leere Gruppen bleiben enthalten
    (als leere Liste) -- kein Weglassen, kein Auffüllen."""
    gruppen = gruppieren(kategorisiert)
    return {
        "ort_plz": fetch.ort_plz,
        "ort_name": fetch.ort_name,
        "anzahl": len(kategorisiert),
        "unsicher": sum(1 for k in kategorisiert if k.unsicher),
        "quellen": list(fetch.abgedeckte_quellen),
        "haendler": list(fetch.gesehene_haendler),
        "hinweise": list(fetch.hinweise),
        "gruppen": [
            {
                "name": g,
                "anzahl": len(gruppen[g]),
                "angebote": [_angebot_dict(ka) for ka in gruppen[g]],
            }
            for g in PRODUKTGRUPPEN
        ],
    }


def rendern(
    fetch: FetchErgebnis,
    kategorisiert: list[KategorisiertesAngebot],
) -> str:
    gruppen = gruppieren(kategorisiert)
    ort = fetch.ort_name or fetch.ort_plz
    zeilen: list[str] = []
    zeilen.append(f"# Angebote {ort} (PLZ {fetch.ort_plz})")
    zeilen.append("")
    zeilen.append(
        f"Quellen: {', '.join(fetch.abgedeckte_quellen) or '—'}  ·  "
        f"{len(kategorisiert)} Angebote"
    )
    zeilen.append("")

    for gruppe in PRODUKTGRUPPEN:
        eintraege = gruppen[gruppe]
        zeilen.append(f"## {gruppe}")
        if not eintraege:
            zeilen.append("_keine Angebote_")
            zeilen.append("")
            continue
        for ka in eintraege:
            zeilen.append(_zeile(ka))
        zeilen.append("")

    zeilen.append("---")
    if fetch.gesehene_haendler:
        zeilen.append(
            "**Beobachtete Händler (datengetrieben, belegt):** "
            + ", ".join(fetch.gesehene_haendler)
            + "."
        )
    zeilen.append(
        "_Abdeckung = was die abgefragten Quellen für diesen Ort hergeben; "
        "Fehlen eines Händlers belegt keine Lücke, sondern nur 'diese Woche/"
        "Abfrage kein Treffer'._"
    )
    for h in fetch.hinweise:
        zeilen.append(f"_{h}_")

    return "\n".join(zeilen).rstrip() + "\n"


def _zeile(ka: KategorisiertesAngebot) -> str:
    a = ka.angebot
    teile: list[str] = []
    if a.marke:
        teile.append(f"**{a.marke}** {a.titel}")
    else:
        teile.append(f"**{a.titel}**")
    if a.menge:
        teile.append(f"({a.menge})")
    if a.preis is not None:
        teile.append(f"— {a.preis:.2f} €".replace(".", ","))
    else:
        teile.append("— Preis fehlt")
    if a.grundpreis:
        teile.append(f"[{a.grundpreis}]")
    if a.gueltig_von or a.gueltig_bis:
        von = a.gueltig_von.isoformat() if a.gueltig_von else "?"
        bis = a.gueltig_bis.isoformat() if a.gueltig_bis else "?"
        teile.append(f"gültig {von}–{bis}")
    teile.append(f"@ {a.haendler}")
    if ka.unsicher:
        teile.append("⚠️ unsicher")
    return "- " + " ".join(teile)
