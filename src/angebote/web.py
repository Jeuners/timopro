"""FastAPI-Web-UI -- dünne Schicht über den bestehenden Modulen.

Der Schnitt bleibt unangetastet und ist hier sogar im Endpoint-Schnitt sichtbar:

  * Stufe 1 -- /api/rohdaten -- ruft NUR den deterministischen Fetch und
    persistiert die belegten Rohdaten. KEIN Key, KEIN LLM.
  * Stufe 2 -- /api/kategorisieren -- liest die gespeicherten Rohdaten und
    führt ausschließlich darauf die LLM-Kategorisierung aus. Sie fetcht NICHT
    erneut und ist gesperrt, solange keine Rohdaten vorliegen.

Die UI ist reine Präsentation; alle harten Regeln (kein Auffüllen, nur Belegtes,
Abbruch statt Drift) leben weiter in den darunterliegenden Modulen.

Start:
    OPENROUTER_API_KEY=... uvicorn angebote.web:app --port 8000
(aus dem src/-Verzeichnis, oder mit PYTHONPATH=src)
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .fehler import AbbruchFehler

app = FastAPI(title="Angebots-Übersicht")

_HTML = (Path(__file__).parent / "web_static" / "index.html").read_text("utf-8")

# In-memory Job-Store für Stufe 2 (LLM, läuft im Thread). Schlicht gehalten --
# ein lokales Single-User-Werkzeug.
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

# Ergebnis-Cache: identische Kategorisierung (PLZ, Modell) kommt sofort, ohne
# erneute LLM-Calls. Im Geist des Projekt-Cachings. In-memory, pro Serverlauf.
_ergebnis_cache: dict[tuple, dict] = {}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _HTML


@app.get("/api/modelle")
def api_modelle(q: str = "") -> list[dict]:
    """Modell-Liste für das Dropdown: Suche oder Top-Free. 'Aktualisieren' = neu rufen."""
    from .modelle import lade_modelle, suche, top_free

    try:
        alle = lade_modelle()
    except Exception as e:  # Netz/SSL -> ehrlich melden, nicht raten
        raise HTTPException(status_code=502, detail=f"Modelle nicht abrufbar: {e}")
    treffer = suche(alle, q) if q else top_free(alle, 8)
    return [
        {"id": m.id, "frei": m.frei, "tools": m.tools, "context": m.context}
        for m in treffer[:25]
    ]


@app.get("/api/ollama-modelle")
def api_ollama_modelle() -> list[dict]:
    """Lokal installierte Ollama-Modelle. Leere Liste, wenn Ollama nicht läuft."""
    from .modelle import lade_ollama_modelle

    return [
        {"id": m.id, "frei": m.frei, "tools": m.tools, "context": m.context}
        for m in lade_ollama_modelle()
    ]


# === Stufe 1: Rohdaten holen & speichern (deterministisch, ohne Key) =========


@app.post("/api/rohdaten")
def api_rohdaten_holen(req: dict) -> dict:
    """Holt belegte Rohdaten (Fetch) und persistiert sie pro PLZ/Woche.

    KEIN LLM, KEIN Key. Bei Spezifitätsmangel / Datenlage-Bruch wird der
    AbbruchFehler ehrlich als 422 mit Ursache/Vorschlag weitergereicht --
    es wird nichts aufgefüllt.
    """
    plz = (req.get("plz") or "").strip()
    if not plz:
        raise HTTPException(status_code=400, detail="PLZ fehlt")

    from .fetch import hole_angebote
    from .speicher import meta_fuer, rohliste_dicts, speichere_rohdaten

    try:
        fetch = hole_angebote(plz)  # deterministisch; AbbruchFehler bei Regel 4
    except AbbruchFehler as e:
        raise HTTPException(status_code=422, detail=e.als_text())
    except Exception as e:  # nichts verstecken -- ehrliche Fehlermeldung
        raise HTTPException(status_code=502, detail=f"Unerwarteter Fehler: {e}")

    speichere_rohdaten(fetch)
    # Frisch kategorisierte Ergebnisse dieser PLZ verwerfen -- Roh-Stand neu.
    for schluessel in [k for k in _ergebnis_cache if k[0] == plz]:
        _ergebnis_cache.pop(schluessel, None)

    meta = meta_fuer(plz) or {}
    return {
        "plz": plz,
        "ort_name": meta.get("ort_name"),
        "anzahl": meta.get("anzahl", len(fetch.angebote)),
        "haendler": meta.get("haendler", list(fetch.gesehene_haendler)),
        "quellen": meta.get("quellen", list(fetch.abgedeckte_quellen)),
        "abgerufen_am": meta.get("abgerufen_am"),
        "hinweise": meta.get("hinweise", list(fetch.hinweise)),
        "angebote": rohliste_dicts(fetch),
    }


@app.get("/api/rohdaten/{plz}")
def api_rohdaten_laden(plz: str) -> dict:
    """Liefert den gespeicherten Roh-Stand der aktuellen Woche oder 404."""
    from .speicher import lade_rohdaten, meta_fuer, rohliste_dicts

    meta = meta_fuer(plz)
    if meta is None:
        raise HTTPException(
            status_code=404, detail=f"keine gespeicherten Rohdaten für PLZ {plz}"
        )
    fetch = lade_rohdaten(plz)
    return {
        "plz": plz,
        "ort_name": meta.get("ort_name"),
        "anzahl": meta.get("anzahl", 0),
        "haendler": meta.get("haendler", []),
        "quellen": meta.get("quellen", []),
        "abgerufen_am": meta.get("abgerufen_am"),
        "hinweise": meta.get("hinweise", []),
        "angebote": rohliste_dicts(fetch) if fetch else [],
    }


# === Stufe 2: Kategorisieren (LLM) -- erst NACH vorhandenen Rohdaten =========


@app.post("/api/kategorisieren")
def api_kategorisieren(req: dict) -> dict:
    """Startet die LLM-Kategorisierung auf den GESPEICHERTEN Rohdaten.

    Gesperrt (400), solange keine Rohdaten zur PLZ vorliegen. Liest sie aus der
    Persistenz -- fetcht NICHT erneut. Status-Polling über /api/lauf/{job_id}.
    """
    plz = (req.get("plz") or "").strip()
    if not plz:
        raise HTTPException(status_code=400, detail="PLZ fehlt")

    from .speicher import lade_rohdaten

    fetch = lade_rohdaten(plz)
    if fetch is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Keine Rohdaten für PLZ {plz}. Zuerst Stufe 1 'Rohdaten holen' "
                "ausführen -- die Kategorisierung arbeitet nur auf belegten Daten."
            ),
        )

    modell = req.get("modell") or None
    anbieter = req.get("anbieter") or "openrouter"
    key = req.get("key") or None
    job_id = uuid.uuid4().hex[:12]

    # Cache-Treffer? Dann sofort als fertiger Job ausliefern, kein neuer Lauf.
    # Anbieter ist Teil des Schlüssels -- dasselbe Modell-Kürzel kann je Anbieter
    # etwas anderes bedeuten.
    treffer = _ergebnis_cache.get((plz, anbieter, modell))
    if treffer is not None:
        with _jobs_lock:
            _jobs[job_id] = {
                "status": "fertig", "phase": "cache", "done": 0, "total": 0,
                "ergebnis": treffer, "fehler": None,
            }
        return {"job_id": job_id, "cache": True}

    with _jobs_lock:
        _jobs[job_id] = {
            "status": "laufend",
            "phase": "kategorisieren",
            "done": 0,
            "total": 0,
            "ergebnis": None,
            "fehler": None,
        }
    t = threading.Thread(
        target=_run_kategorisieren,
        args=(job_id, plz, fetch, modell, anbieter, key),
        daemon=True,
    )
    t.start()
    return {"job_id": job_id}


@app.get("/api/lauf/{job_id}")
def api_status(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="unbekannter Job")
    return job


def _run_kategorisieren(job_id, plz, fetch, modell, anbieter, key) -> None:
    """LLM-Schritt im Hintergrund. Arbeitet auf den geladenen Rohdaten.

    Verändert die Angebotsdaten nicht (sie sind frozen); übernimmt vom Modell
    nur Gruppe + Unsicherheits-Flag.
    """
    job = _jobs[job_id]
    try:
        from .kategorisieren import baue_kategorisierer, kategorisiere
        from .uebersicht import als_struktur

        kt = baue_kategorisierer(anbieter, modell, api_key=key)
        # Tatsächlich genutztes Modell (Default je Anbieter aufgelöst) -- für die
        # sichtbare Herkunft im Ergebnis.
        modell_genutzt = getattr(kt, "_modell", modell)

        def fort(done, total):
            job["done"] = done
            job["total"] = total

        kat = kategorisiere(list(fetch.angebote), kt, fortschritt=fort)

        job["ergebnis"] = als_struktur(
            fetch, kat, modell=modell_genutzt, anbieter=anbieter
        )
        job["status"] = "fertig"
        _ergebnis_cache[(plz, anbieter, modell)] = job["ergebnis"]
    except AbbruchFehler as e:
        job["status"] = "fehler"
        job["fehler"] = e.als_text()
    except Exception as e:  # nichts verstecken -- ehrliche Fehlermeldung
        job["status"] = "fehler"
        job["fehler"] = f"Unerwarteter Fehler: {e}"
