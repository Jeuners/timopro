# CLAUDE.md -- Angebots-Übersicht

Leitfaden für die Entwicklung dieses Projekts mit Claude Code.

## Was dieses Projekt ist

Eine sachliche, ortskonkrete Übersicht der wöchentlichen Supermarkt- und
Discounter-Angebote, sortiert nach Produktgruppen. Kein Hochglanzprospekt
einzelner Händler, sondern eine händlerübergreifende, neutrale Liste:
"Was ist diese Woche an Ort X im Angebot, geordnet nach Kategorie."

## Das Leitprinzip: der Schnitt

Diese Aufgabe sieht nach einer KI-Aufgabe aus. Sie ist es nur zur Hälfte.
Sie zerfällt in zwei grundverschiedene Teilprobleme, die strikt getrennt
gehören:

1. **Daten holen** (ortskonkret, händlerübergreifend) -- das ist
   **deterministisch**. Hier wird KI eingespart. Ein HTTP-Abruf / Parser
   leistet das exakt und reproduzierbar. Ein LLM würde hier nur Preise und
   Gültigkeiten halluzinieren. Dieser Teil enthält **keine** LLM-Aufrufe.

2. **Kategorisieren** (flacher Angebots-Stream → saubere Produktgruppen) --
   das ist die **echte Ambiguität**: "Ist Toffifee Süßwaren? Ist Schwarzwälder
   Schinken Fleisch/Wurst? Gehört eine Blühpflanze überhaupt in eine
   Lebensmittel-Übersicht?" Genau hier ist ein LLM das richtige Werkzeug --
   und nur hier.

> Merksatz: Vor KI muss man erst einmal KI einsparen. Aber dort, wo nur sie
> passt, muss man sie auch einsetzen. Wer die ganze Aufgabe dem Modell gibt,
> bekommt Fiktion. Wer sie ganz deterministisch löst, scheitert an der
> Kategorisierung. Richtig ist die Arbeitsteilung.

Dieser Schnitt ist nicht verhandelbar. Er ist die Architektur des Projekts,
nicht eine Stilpräferenz. Vermische die beiden Teile nicht.

## Architektur statt Präferenz

Qualitätsregeln werden hier **festverdrahtet**, nicht "mitgedacht". Eine Regel,
die nur als höfliche Bitte im Code steht ("möglichst keine erfundenen Preise"),
bricht unter Druck still weg. Eine Regel, die als prüfbare Bedingung im
Datenfluss steht, hält.

Konkrete Konsequenzen, die jederzeit gelten:

- **Kein Auffüllen.** Wenn für eine Produktgruppe keine belegten Angebote
  vorliegen, wird "keine Daten" ausgegeben -- niemals ein plausibel klingendes
  Beispiel erfunden.
- **Jedes ausgegebene Angebot ist belegt.** Preis, Gültigkeit und Händler
  stammen aus dem abgerufenen Datensatz, nicht aus dem Modell. Wenn ein Feld
  fehlt, wird es als fehlend markiert, nicht geraten.
- **Abbruch statt stiller Drift.** Wenn die Datenlage die Anforderung nicht
  hergibt (z. B. kein Treffer für den Ort), bricht das Programm mit einer
  klaren Meldung ab und nennt die Ursache und einen Erweiterungsvorschlag.
  Es liefert kein "irgendwie vollständig aussehendes" Ergebnis.

Diese drei Punkte sind der Grund, warum "die KI soll sagen, wenn sie scheitert"
hier funktioniert: nicht weil das Modell Einsicht hätte, sondern weil eine
externe, prüfbare Bedingung es erzwingt.

## Skills

Das Projekt nutzt zwei Skills (in `.claude/skills/`), die exakt dem Schnitt
folgen:

- **angebote-fetch** -- deterministischer Datenabruf. Keine LLM-Aufrufe.
- **angebote-kategorisieren** -- LLM-gestützte Einordnung in Produktgruppen.

Lies die jeweilige `SKILL.md`, bevor du an dem zugehörigen Teil arbeitest.
Die SKILL.md ist die verbindliche Spezifikation für ihren Bereich.

## Tech-Kontext

- Sprache: **Python** (FastAPI-nah).
- Öffentlicher Stack-Bezug, falls relevant: FastAPI, Qdrant, A2A.
- Datenquellen-Kandidaten für den Fetch-Teil: Angebots-Aggregatoren, die nach
  Ort/PLZ filtern (z. B. marktguru, kaufda, MeinProspekt). Discounter wie
  Aldi/Lidl liefern oft nicht an Aggregatoren -- das ist ein bekanntes
  Abdeckungsloch und gehört ehrlich als solches ausgewiesen, nicht kaschiert.

## Arbeitsweise mit Claude Code

- Beginne jede Aufgabe damit, den relevanten Teil dieses Dokuments und die
  passende SKILL.md zu lesen.
- Halte den Schnitt sauber: kein LLM-Aufruf im Fetch-Teil, kein heimliches
  Daten-"Reparieren" im Kategorisier-Teil.
- Wenn eine Anforderung den Schnitt verletzen würde, benenne den Konflikt,
  bevor du Code schreibst.
- Schreibe Tests für die Architektur-Regeln (kein Auffüllen, Abbruch bei
  leerer Datenlage), nicht nur für den Happy Path.
