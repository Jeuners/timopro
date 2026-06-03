---
name: angebote-kategorisieren
description: >
  Ordnet einen flachen, bereits beschafften Angebots-Stream in saubere
  Produktgruppen. Dies ist der EINZIGE Teil des Projekts, in dem ein LLM
  eingesetzt wird -- weil die Einordnung genuin unscharf ist. Verwenden, wenn
  normalisierte Angebote (aus angebote-fetch) in eine nach Kategorien
  geordnete Übersicht gebracht werden sollen. Trigger: "kategorisieren",
  "nach Produktgruppen sortieren", "Übersicht bauen".
---

# angebote-kategorisieren

## Zweck

Nimm die normalisierten, belegten Angebote aus `angebote-fetch` und ordne jedes
einer Produktgruppe zu. Ergebnis ist eine nach Kategorien gruppierte Übersicht.
Dieser Skill **verändert keine Angebotsdaten** -- er fügt nur die
Gruppenzuordnung hinzu.

## Warum hier ein LLM sinnvoll ist (und nur hier)

Die Zuordnung ist die echte Ambiguität der Aufgabe. Regelbasiert ("enthält
'Käse' → Molkereiprodukte") scheitert an Toffifee, Schwarzwälder Schinken,
Grundnahrungsmitteln mit Markennamen, Non-Food in Supermarktprospekten. Diese
unscharfe Einordnung ist exakt die Stärke eines Sprachmodells. Deshalb läuft
**nur** dieser Schritt über ein LLM -- nicht die Datenbeschaffung.

## Harte Regeln (Architektur, nicht Präferenz)

1. **Daten sind unantastbar.** Das LLM darf Titel, Preis, Gültigkeit, Händler
   NICHT verändern, korrigieren oder ergänzen. Es vergibt ausschließlich eine
   Produktgruppe. Wenn ein Preis fehlt, bleibt er fehlend -- nicht "ergänzen".
2. **Geschlossene Kategorienliste.** Das Modell wählt aus einer fest
   definierten Liste von Produktgruppen (s. u.). Es erfindet keine neuen
   Kategorien. Passt ein Artikel in keine, kommt er in `Sonstiges` bzw.
   `Non-Food`.
3. **Eine Gate-Prüfung pro Angebot.** Jedes Angebot durchläuft die Zuordnung
   einzeln. Wenn das Modell bei einem Artikel unsicher ist, markiert es ihn als
   `unsicher: true` mit der wahrscheinlichsten Gruppe -- es rät nicht still.
4. **Kein stilles Absenken bei vielen Elementen.** Bei langen Listen darf die
   Zuordnungsqualität nicht zum Ende hin abfallen. Verarbeite in kleinen
   Batches mit gleichbleibendem Schema; fülle nie eine Gruppe auf, um sie
   "ausgewogen" aussehen zu lassen.

## Produktgruppen (Startliste, anpassbar)

```
Obst & Gemüse
Fleisch & Wurst
Fisch
Molkereiprodukte & Eier
Brot & Backwaren
Grundnahrungsmittel (Nudeln, Reis, Mehl, Konserven)
Süßwaren & Snacks
Getränke (alkoholfrei)
Alkoholische Getränke
Tiefkühl
Drogerie & Haushalt
Non-Food (Kleidung, Spielzeug, Garten, Technik)
Sonstiges
```

Die Liste lebt in einer Config, nicht im Prompt-Text -- so kann das Team sie
anpassen, ohne die Logik zu berühren.

## LLM-Aufruf

- Übergib dem Modell pro Batch nur das Nötige: Titel, Marke, Menge. NICHT
  Preis/Gültigkeit (die sind für die Einordnung irrelevant und sollen nicht
  versehentlich verändert zurückkommen).
- Lass das Modell strukturiert antworten (z. B. JSON: `{id, gruppe,
  unsicher}`), und mappe das Ergebnis zurück auf die unveränderten
  Original-Angebote über eine stabile ID. Übernimm vom Modell **nur** Gruppe
  und Unsicherheits-Flag -- alles andere kommt aus dem Originaldatensatz.
- System-Vorgabe an das Modell: geschlossene Kategorienliste, keine neuen
  Kategorien, bei Unsicherheit Flag setzen statt raten.
- Liefert das Modell trotzdem eine Gruppe außerhalb der Liste, wird sie nicht
  übernommen: der Artikel landet in `Sonstiges` und wird als `unsicher`
  markiert. Die geschlossene Liste ist eine prüfbare Bedingung im Code, keine
  Bitte an das Modell.

## Ausgabe

Eine nach Produktgruppen geordnete Übersicht. Pro Gruppe die zugehörigen
Angebote mit ihren belegten Feldern. Leere Gruppen werden als "keine Angebote"
ausgewiesen -- nicht weggelassen und nicht aufgefüllt. Unsicher zugeordnete
Artikel werden sichtbar markiert, damit ein Mensch nachsehen kann.

## Tests

- Daten-Integrität: Preis/Gültigkeit/Händler nach Kategorisierung identisch zu
  vorher (Property-Test über den ganzen Stream).
- Geschlossene Liste: keine Gruppe außerhalb der Config taucht auf.
- Unsicherheit: bewusst mehrdeutige Artikel (z. B. "Pflanzendrink") werden
  geflaggt, nicht still einsortiert.

## Was dieser Skill NICHT tut

- Keine Datenbeschaffung (das macht angebote-fetch).
- Keine Preis-/Qualitätsbewertung.
- Kein Verändern, Reparieren oder Ergänzen von Angebotsdaten.
