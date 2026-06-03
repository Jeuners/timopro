"""FastAPI-Web-UI -- dünne Schicht über den bestehenden Modulen.

Der Schnitt bleibt unangetastet: dieser Server ruft `fetch` (deterministisch)
und `kategorisieren` (LLM) auf, vermischt aber nichts. Die UI ist reine
Präsentation; alle harten Regeln (kein Auffüllen, nur Belegtes, Abbruch statt
Drift) leben weiter in den darunterliegenden Modulen.

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

# In-memory Job-Store. Schlicht gehalten -- ein lokales Single-User-Werkzeug.
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

# Ergebnis-Cache: identischer Lauf (PLZ, Modell, no_llm) kommt sofort, ohne
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


@app.post("/api/lauf")
def api_lauf(req: dict) -> dict:
    plz = (req.get("plz") or "").strip()
    if not plz:
        raise HTTPException(status_code=400, detail="PLZ fehlt")
    modell = req.get("modell") or None
    no_llm = bool(req.get("no_llm"))
    job_id = uuid.uuid4().hex[:12]

    # Cache-Treffer? Dann sofort als fertiger Job ausliefern, kein neuer Lauf.
    treffer = _ergebnis_cache.get((plz, modell, no_llm))
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
            "phase": "fetch",
            "done": 0,
            "total": 0,
            "ergebnis": None,
            "fehler": None,
        }
    t = threading.Thread(
        target=_run_job,
        args=(
            job_id,
            plz,
            modell,
            req.get("anbieter") or "openrouter",
            no_llm,
            req.get("key") or None,
        ),
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


def _run_job(job_id, plz, modell, anbieter, no_llm, key) -> None:
    job = _jobs[job_id]
    try:
        from .fetch import hole_angebote
        from .modell import KategorisiertesAngebot
        from .uebersicht import als_struktur

        fetch = hole_angebote(plz)  # deterministisch; AbbruchFehler bei Regel 4

        if no_llm:
            # Ohne LLM: belegte Rohliste, sichtbar als unkategorisiert markiert.
            from .config import FALLBACK_GRUPPE

            kat = [
                KategorisiertesAngebot(a, FALLBACK_GRUPPE, unsicher=True)
                for a in fetch.angebote
            ]
        else:
            from .kategorisieren import baue_kategorisierer, kategorisiere

            job["phase"] = "kategorisieren"
            kt = baue_kategorisierer(anbieter, modell, api_key=key)

            def fort(done, total):
                job["done"] = done
                job["total"] = total

            kat = kategorisiere(list(fetch.angebote), kt, fortschritt=fort)

        job["ergebnis"] = als_struktur(fetch, kat)
        job["status"] = "fertig"
        _ergebnis_cache[(plz, modell, no_llm)] = job["ergebnis"]
    except AbbruchFehler as e:
        job["status"] = "fehler"
        job["fehler"] = e.als_text()
    except Exception as e:  # nichts verstecken -- ehrliche Fehlermeldung
        job["status"] = "fehler"
        job["fehler"] = f"Unerwarteter Fehler: {e}"
