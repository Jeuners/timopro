"""Fetch-Orchestrator. Ort rein, belegte Angebote raus. KEIN LLM.

Trennt sauber zwei Fälle, die oberflächlich gleich aussehen:

  * KEINE Quelle deckt den Ort ab / Ort nicht auflösbar -> AbbruchFehler (Regel 4).
  * Quellen liefen, lieferten aber nichts -> leeres, ehrliches Ergebnis
    (kein Auffüllen). Die Übersicht zeigt dann "keine Angebote".
"""

from __future__ import annotations

from .config import ORTSNAME_PLZ
from .fehler import AbbruchFehler
from .modell import Angebot, FetchErgebnis
from .quellen.basis import Ort, QuelleAdapter


def aufloesen_ort(eingabe: str) -> Ort:
    """Löst eine Eingabe (PLZ oder Ortsname) deterministisch zu einem Ort auf.

    5-stellige Ziffernfolge -> PLZ. Bekannter Ortsname -> hinterlegte PLZ.
    Sonst Abbruch (Regel 4) -- es wird KEINE PLZ geraten.
    """
    roh = (eingabe or "").strip()
    if roh.isdigit() and len(roh) == 5:
        return Ort(plz=roh, name=None)

    schluessel = roh.lower()
    if schluessel in ORTSNAME_PLZ:
        return Ort(plz=ORTSNAME_PLZ[schluessel], name=roh)

    raise AbbruchFehler(
        schwelle="Ortsauflösung",
        ursache=(
            f"'{eingabe}' ist weder eine 5-stellige PLZ noch ein hinterlegter Ortsname"
        ),
        vorschlag=(
            "eine 5-stellige PLZ angeben (z. B. 60487). Ortsnamen sind nur für "
            "eine kleine Auswahl großer Städte hinterlegt -- bewusst wird keine "
            "PLZ geraten."
        ),
    )


def hole_angebote(
    eingabe: str,
    quellen: list[QuelleAdapter] | None = None,
) -> FetchErgebnis:
    """Beschafft belegte Angebote für einen Ort über alle abdeckenden Quellen."""
    if quellen is None:
        quellen = standard_quellen()
    if not quellen:
        raise AbbruchFehler(
            schwelle="Quellen",
            ursache="keine Quelle konfiguriert",
            vorschlag="mindestens einen Adapter in standard_quellen() registrieren",
        )

    ort = aufloesen_ort(eingabe)

    abdeckend = [q for q in quellen if q.deckt_ab(ort)]
    if not abdeckend:
        raise AbbruchFehler(
            schwelle="Ortsabdeckung",
            ursache=f"keine der {len(quellen)} Quellen deckt PLZ {ort.plz} ab",
            vorschlag="andere PLZ in der Nähe versuchen oder weitere Quelle ergänzen",
        )

    alle: list[Angebot] = []
    gelaufen: list[str] = []
    hinweise: list[str] = []
    for q in abdeckend:
        gelaufen.append(q.name)
        treffer = q.hole(ort)  # AbbruchFehler propagiert bewusst nach oben
        if not treffer:
            hinweise.append(f"Quelle '{q.name}': 0 Angebote (kein Auffüllen).")
        # Ehrliche Abdeckungs-Notiz der Quelle übernehmen, falls vorhanden:
        notiz = getattr(q, "abdeckungshinweis", None)
        if notiz:
            hinweise.append(notiz)
        alle.extend(treffer)

    gesehene = tuple(sorted({a.haendler for a in alle}))
    return FetchErgebnis(
        ort_plz=ort.plz,
        ort_name=ort.name,
        angebote=tuple(alle),
        abgedeckte_quellen=tuple(gelaufen),
        gesehene_haendler=gesehene,
        hinweise=tuple(hinweise),
    )


def standard_quellen() -> list[QuelleAdapter]:
    """Registry der aktiven Quellen. Hier werden Adapter ein-/ausgehängt."""
    from .quellen.marktguru import MarktguruAdapter

    return [MarktguruAdapter()]
