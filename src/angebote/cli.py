"""CLI-Einstieg: Ort rein, geordnete Übersicht raus.

Der Schnitt bleibt auch hier sichtbar: erst `fetch` (deterministisch), dann --
nur falls gewünscht und Schlüssel vorhanden -- `kategorisieren` (LLM).
"""

from __future__ import annotations

import argparse
import os
import sys

from .fehler import AbbruchFehler
from .fetch import hole_angebote
from .modell import KategorisiertesAngebot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="angebote",
        description="Ortskonkrete, händlerübergreifende Angebots-Übersicht nach Produktgruppen.",
    )
    parser.add_argument(
        "ort",
        nargs="?",
        help="PLZ (5-stellig) oder hinterlegter Ortsname",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="ohne Kategorisierung: flache, belegte Liste (kein LLM, kein Schlüssel nötig)",
    )
    parser.add_argument(
        "--anbieter",
        choices=("openrouter", "anthropic"),
        default=None,
        help="LLM-Anbieter erzwingen; ohne Angabe automatisch nach gesetztem Key",
    )
    parser.add_argument(
        "--modell",
        default=None,
        help="Modell-ID überschreiben (Default je Anbieter)",
    )
    parser.add_argument(
        "--modelle",
        nargs="?",
        const="",
        default=None,
        metavar="SUCHE",
        help="OpenRouter-Modelle auflisten und beenden; optional Suchbegriff "
        "(ohne Begriff: Top-5 Free, tool-fähig)",
    )
    parser.add_argument(
        "--modell-waehlen",
        action="store_true",
        help="vor dem Lauf das OpenRouter-Modell interaktiv wählen (Liste/Suche/Update)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="den Produkt->Kategorie-Cache nicht nutzen (alles neu kategorisieren)",
    )
    args = parser.parse_args(argv)

    # Reiner Listen-/Suchmodus -- braucht keinen Ort und keinen Key.
    if args.modelle is not None:
        return _liste_modelle(args.modelle)

    if not args.ort:
        parser.error("Ort fehlt (PLZ oder Ortsname) -- oder nutze --modelle zum Auflisten.")

    try:
        fetch = hole_angebote(args.ort)
    except AbbruchFehler as e:
        print(e.als_text(), file=sys.stderr)
        return 2

    if args.no_llm:
        _druck_flach(fetch)
        return 0

    anbieter = args.anbieter or _anbieter_aus_umgebung()
    if anbieter is None:
        print(
            "Abbruch (Kategorisierung): kein LLM-Key gesetzt "
            "(OPENROUTER_API_KEY oder ANTHROPIC_API_KEY).\n"
            "  Vorschlag: einen Key setzen ODER mit --no-llm die belegte Rohliste ausgeben.",
            file=sys.stderr,
        )
        return 2

    modell = args.modell
    if args.modell_waehlen:
        if anbieter != "openrouter":
            print(
                "Hinweis: --modell-waehlen ist für OpenRouter gedacht; nutze --anbieter openrouter.",
                file=sys.stderr,
            )
            return 2
        from .modellauswahl import waehle_modell_interaktiv

        modell = waehle_modell_interaktiv()
        if not modell:
            print("Keine Modellwahl getroffen -- abgebrochen.", file=sys.stderr)
            return 2

    from .kategorisieren import baue_kategorisierer, kategorisiere
    from .uebersicht import rendern

    cache = None
    if not args.no_cache:
        from .produktcache import ProduktCache

        cache = ProduktCache()
    stat: dict = {}
    try:
        kat = kategorisiere(
            list(fetch.angebote),
            baue_kategorisierer(anbieter, modell),
            cache=cache,
            statistik=stat,
        )
    except AbbruchFehler as e:
        print(e.als_text(), file=sys.stderr)
        return 2

    if cache is not None:
        print(
            f"({stat.get('aus_cache', 0)} aus Cache · {stat.get('neu', 0)} neu kategorisiert)",
            file=sys.stderr,
        )
    print(rendern(fetch, kat))
    return 0


def _liste_modelle(suchbegriff: str) -> int:
    from .modelle import lade_modelle, suche, top_free

    try:
        alle = lade_modelle()
    except Exception as e:
        print(f"Modelle nicht abrufbar: {e}", file=sys.stderr)
        return 2

    if suchbegriff:
        treffer = suche(alle, suchbegriff)[:20]
        print(f"Suche '{suchbegriff}' (max. 20):")
    else:
        treffer = top_free(alle, 5)
        print("Top-5 Free (tool-fähig, Heuristik):")

    if not treffer:
        print("  (keine Treffer)")
    for i, m in enumerate(treffer, 1):
        ctx = f"{m.context:,}".replace(",", ".") if m.context else "?"
        frei = "FREE" if m.frei else "paid"
        warn = "" if m.tools else "  ⚠️ kein tool-calling"
        print(f"  {i}) {m.id}  [{frei}, ctx {ctx}]{warn}")
    return 0


def _anbieter_aus_umgebung() -> str | None:
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


def _druck_flach(fetch) -> None:
    ort = fetch.ort_name or fetch.ort_plz
    print(f"# Angebote {ort} (PLZ {fetch.ort_plz}) — Rohliste, unkategorisiert")
    print(f"Quellen: {', '.join(fetch.abgedeckte_quellen) or '—'}\n")
    if not fetch.angebote:
        print("_keine Angebote (kein Auffüllen)_")
    for a in fetch.angebote:
        preis = f"{a.preis:.2f} €".replace(".", ",") if a.preis is not None else "Preis fehlt"
        marke = f"{a.marke} " if a.marke else ""
        menge = f" ({a.menge})" if a.menge else ""
        print(f"- {marke}{a.titel}{menge} — {preis} @ {a.haendler}")
    if fetch.gesehene_haendler:
        print("\nBeobachtete Händler: " + ", ".join(fetch.gesehene_haendler))
    for h in fetch.hinweise:
        print(f"# {h}")


if __name__ == "__main__":
    raise SystemExit(main())
