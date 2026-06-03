"""Der Schnitt als Test: im Fetch-Teil darf KEIN LLM geladen werden.

Geprüft in einem frischen Interpreter: nach dem Import des kompletten
Fetch-Pfads (fetch + marktguru-Adapter) darf 'anthropic' nicht in sys.modules
stehen. So bleibt die Trennung 'kein LLM im Fetch-Teil' eine prüfbare Bedingung.
"""

import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def test_fetch_teil_laedt_kein_anthropic():
    code = (
        "import sys; "
        "import angebote.fetch; "
        "import angebote.quellen.marktguru; "
        "assert 'anthropic' not in sys.modules, "
        "'Fetch-Teil hat anthropic geladen -- Schnitt verletzt'; "
        "print('ok')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(SRC),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout


def test_marktguru_quelltext_nennt_anthropic_nicht():
    quelltext = (SRC / "angebote" / "quellen" / "marktguru.py").read_text("utf-8")
    assert "anthropic" not in quelltext.lower()
