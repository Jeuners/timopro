"""E2E-Test: die LLM-Konfiguration (Anbieter + Modell) überlebt einen Reload.

Echter Browser (Playwright) gegen einen frisch gestarteten Server. Prüft das
Verhalten, das im UI vorher fehlte: nach Umschalten auf Ollama und Neuladen darf
die UI NICHT auf den OpenRouter-Default zurückspringen.

Wird übersprungen, wenn Playwright/Chromium nicht installiert ist.
"""

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"


def _freier_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def server():
    port = _freier_port()
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "angebote.web:app",
         "--port", str(port), "--log-level", "warning"],
        cwd=str(SRC), env=env,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/", timeout=1)
                break
            except Exception:
                time.sleep(0.25)
        else:
            raise RuntimeError("Server kam nicht hoch")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


def _chromium_da() -> bool:
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            b.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _chromium_da(), reason="Chromium für Playwright nicht installiert")
def test_anbieter_persistiert_ueber_reload(server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server)
        page.wait_for_selector("#anbieter", state="attached")

        # Konfig-Panel aufklappen (der Anbieter-Select liegt darin), dann
        # auf Ollama umschalten -> löst change-Event + merkeWahl() aus.
        page.evaluate("document.getElementById('config').open = true")
        page.select_option("#anbieter", "ollama")
        page.wait_for_timeout(1000)

        # Reload -> init() muss die gemerkte Wahl wiederherstellen.
        page.reload()
        page.wait_for_selector("#anbieter", state="attached")
        page.wait_for_timeout(1000)

        wert = page.eval_on_selector("#anbieter", "el => el.value")
        assert wert == "ollama", f"Anbieter nach Reload = {wert!r}, erwartet 'ollama'"
        browser.close()
