# Angebots-Übersicht

Ortskonkrete, händlerübergreifende Übersicht wöchentlicher Supermarkt-Angebote,
geordnet nach Produktgruppen. Neutral, nicht als Hochglanzprospekt.

## Der Gedanke

Die Aufgabe sieht nach einer KI-Aufgabe aus, ist es aber nur zur Hälfte. Sie
zerfällt in zwei strikt getrennte Teile:

1. **Daten holen** -- deterministisch, ohne LLM. (Skill `angebote-fetch`)
2. **Kategorisieren** -- die echte Ambiguität, hier gehört das LLM hin.
   (Skill `angebote-kategorisieren`)

Wer alles dem Modell gibt, bekommt erfundene Preise. Wer alles deterministisch
löst, scheitert an der Einordnung. Die Architektur erzwingt den Schnitt.

Der zweite Punkt, der dieses Projekt trägt: Qualitätsregeln stehen nicht als
gut gemeinte Bitten im Code, sondern als prüfbare Bedingungen -- kein
Auffüllen, nur Belegtes, Abbruch statt stiller Drift. Genau dadurch "sagt das
System, wenn es scheitert": nicht aus Einsicht des Modells, sondern weil eine
externe Bedingung es erzwingt.

## Entwicklung mit Claude Code

`CLAUDE.md` ist der verbindliche Leitfaden. Die beiden `SKILL.md` in
`.claude/skills/` sind die Spezifikationen der zwei Teile. Claude Code liest
sie automatisch -- beim Arbeiten am jeweiligen Teil zuerst die passende
SKILL.md lesen.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Nutzung

```bash
# PLZ direkt (immer verlässlich):
python -m angebote 60487

# Ortsname (nur für die in config.py hinterlegte Auswahl großer Städte;
# unbekannter Ort -> ehrlicher Abbruch mit Vorschlag, keine Notlösung):
python -m angebote "Frankfurt"

# Ohne Kategorisierung (kein LLM, flache belegte Liste):
python -m angebote 60487 --no-llm
```

Der Kategorisier-Schritt braucht `ANTHROPIC_API_KEY` in der Umgebung. Fehlt er
und es wird kein `--no-llm` gesetzt, bricht das Programm ehrlich ab, statt
ungeordnet weiterzulaufen.

## Stand der Implementierung (ehrlich)

- `requirements.txt` -- **vorhanden**.
- `src/angebote/` -- **vorhanden**: Datenmodell, Adapter-Schnittstelle,
  Fetch-Orchestrator, Kategorisier-Schritt, Übersicht-Renderer, CLI.
- `tests/` -- **vorhanden**: Architektur-Tests (kein Auffüllen, Abbruch bei
  leerem/unauflösbarem Ort, Daten-Integrität nach Kategorisierung,
  geschlossene Kategorienliste, Unsicherheits-Flag, Schnitt-Test "kein LLM im
  Fetch-Teil"). Laufen offline, ohne Netz und ohne LLM.
- **Live bestätigt:** der marktguru-Adapter wurde gegen die echte API getestet
  (PLZ 60487) und liefert reale, belegte Angebote (u. a. ALDI SÜD, PENNY, Lidl,
  REWE, Kaufland, nahkauf). Erkenntnisse aus dem echten Lauf, die direkt in den
  Code geflossen sind:
  - `offers/search` ist query-orientiert -- leeres `q` liefert 0 Treffer. Der
    Adapter aggregiert daher über Kategorie-Seedbegriffe (config) und weist
    diese **Teilabdeckung** ehrlich aus, statt Vollständigkeit zu behaupten.
  - Die pauschale Annahme "Aldi/Lidl fehlen bei Aggregatoren" wurde von den
    Daten **widerlegt** (beide sind enthalten). Die Abdeckung wird deshalb
    **datengetrieben** ausgewiesen (beobachtete Händler), nicht hartkodiert.
  - marktgurus Marken-Sentinel `thisisnobrand123` wird als "keine Marke"
    behandelt, nicht als Beleg durchgereicht.
- **Voraussetzungen für den Live-Lauf:** installiertes `requests` (certifi für
  TLS), erreichbares Netz, von der Seite lesbare API-Schlüssel. Fehlt eines
  davon, ist das der vorgesehene Abbruchfall (Regel 4) mit *zutreffend*
  benannter Ursache -- keine Krücke.

## Struktur

```
CLAUDE.md                                  Leitfaden / Architektur
README.md                                  dieses Dokument
requirements.txt                           Abhängigkeiten
.claude/skills/angebote-fetch/             Spec: deterministischer Datenabruf
.claude/skills/angebote-kategorisieren/    Spec: LLM-gestützte Einordnung
src/angebote/                              Implementierung
  modell.py        eingefrorenes Angebot-Datenmodell
  fehler.py        AbbruchFehler (Regel 4)
  config.py        Quellenliste, Produktgruppen, Orts-Auflösung
  quellen/         ein Adapter pro Quelle (rein = Ort, raus = [Angebot])
    basis.py       Adapter-Schnittstelle + Ort
    marktguru.py   erster echter Adapter, geprüfter Ortsbezug
  fetch.py         Orchestrator (Ort rein, belegte Angebote raus)
  kategorisieren.py LLM-Schritt hinter einer Schnittstelle (offline testbar)
  uebersicht.py    Gruppierung + Rendering
  cli.py / __main__.py  CLI-Einstieg
tests/                                     Architektur-Tests
```
