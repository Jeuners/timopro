---
name: angebote-fetch
description: >
  Deterministischer Abruf wöchentlicher Supermarkt-/Discounter-Angebote für
  einen konkreten Ort. Verwenden, wenn aktuelle Angebotsdaten beschafft werden
  sollen. Dieser Skill enthält KEINE LLM-Aufrufe -- er holt, parst und
  normalisiert nur. Trigger: "Angebote holen", "Daten für Ort X", "Prospekte
  abrufen", Aufbau/Pflege der Datenbeschaffung.
---

# angebote-fetch

## Zweck

Beschaffe für einen gegebenen Ort (PLZ oder Ortsname) die aktuell gültigen
Angebote, händlerübergreifend, und gib sie als normalisierten, belegten
Datensatz zurück. Nichts wird interpretiert, kategorisiert oder bewertet --
das ist Aufgabe des Skills `angebote-kategorisieren`.

## Harte Regeln (Architektur, nicht Präferenz)

Diese Regeln gelten unabhängig von Kontext und Plausibilität:

1. **Keine LLM-Aufrufe.** Dieser Teil ist rein deterministisch. Wenn du
   versucht bist, ein Modell "zum Aufräumen" einzusetzen, ist das der falsche
   Skill -- halte an.
2. **Nur Belegtes.** Jedes zurückgegebene Angebot trägt seine Quelle (Händler,
   Quell-URL/-ID, Abrufzeitpunkt). Felder, die in der Quelle fehlen, werden als
   `null`/fehlend markiert -- niemals geraten oder geschätzt.
3. **Kein Auffüllen.** Wenn eine Quelle nichts liefert, wird das als leeres
   Ergebnis dieser Quelle gemeldet, nicht durch Beispiele ersetzt.
4. **Abbruch bei Spezifitätsmangel.** Wenn der Ort nicht aufgelöst werden kann
   oder keine Quelle für den Ort filtert, brich mit einer klaren Meldung ab:
   Schwelle (welche), Ursache (Ort nicht auflösbar / keine Quelle deckt Ort ab),
   konkreter Vorschlag (z. B. größerer Ort in der Nähe, andere Quelle).
   Liefere kein ortsfremdes Ergebnis als Notlösung.

## Datenmodell

Ein normalisiertes Angebot (Vorschlag, anpassbar):

```python
@dataclass
class Angebot:
    titel: str               # Produktname, wie in der Quelle
    marke: str | None        # falls vorhanden
    preis: float | None      # in EUR; None wenn nicht eindeutig parsebar
    grundpreis: str | None    # z. B. "1 kg = 4,44 EUR", roh übernommen
    menge: str | None        # z. B. "200g Packung", roh übernommen
    gueltig_von: date | None
    gueltig_bis: date | None
    haendler: str            # Pflicht
    quelle: str              # URL oder Quell-ID, Pflicht
    abgerufen_am: datetime    # Pflicht
    # bewusst KEIN feld "produktgruppe" -- das setzt der andere skill
```

Das Fehlen eines `produktgruppe`-Felds ist Absicht: Die Trennung der beiden
Verantwortungen ist im Datenmodell verankert. In der Implementierung ist
`Angebot` zusätzlich **eingefroren** (`frozen=True`) -- der Kategorisier-Schritt
*kann* die Daten damit nicht verändern, nicht nur *soll* es nicht.

## Quellen

Kandidaten sind Angebots-Aggregatoren mit Ortsfilter. Wichtige bekannte
Eigenheiten:

- Der Ortsfilter steckt bei vielen Aggregatoren in Session/Cookie, nicht in der
  URL -- ein roher Abruf ohne Standort liefert ggf. bundesweite Angebote.
  Stelle den Ortsbezug explizit her und prüfe ihn, statt ihm zu vertrauen.
- Manche Quellen liefern strukturierte Felder (Titel, Marke, Preis, Gültigkeit,
  Händler) gut parsebar; andere nur als Bild-Prospekt. Bild-Prospekte sind
  außerhalb des Scopes dieses Skills, solange keine strukturierte Quelle
  existiert -- in dem Fall greift Regel 4 (Abbruch + ehrlicher Hinweis).
- Discounter (Aldi, Lidl) sind bei Aggregatoren oft unterrepräsentiert. Das
  ist ein Abdeckungsloch, das im Ergebnis ehrlich ausgewiesen wird
  ("Discounter X nicht abgedeckt"), nicht kaschiert.

Halte die konkrete Quellenliste in einem Config-/Adapter-Modul, damit Quellen
ausgetauscht werden können, ohne die Kernlogik anzufassen. Ein Adapter pro
Quelle (gleiche Schnittstelle: rein = Ort, raus = Liste[Angebot]).

## Erwartetes Scheitern (Regel 4 ist der Normalfall, nicht der Ausnahmefall)

Beim Abruf realer Aggregatoren ist Scheitern eingeplant, nicht überraschend.
Die folgenden Fälle sind **vorgesehene Abbruchfälle** -- es wird kein brüchiger
Workaround gebaut, der "irgendwie etwas" liefert:

- **Ortsfilter in Session/Cookie statt URL.** Liefert eine Quelle trotz
  gesetztem Ort erkennbar bundesweite statt ortsbezogene Angebote, ist der
  Ortsbezug *nicht verifiziert*. Dann bricht der Adapter ab (Regel 4) --
  er gibt nicht ein bundesweites Ergebnis als "Ort X" aus.
- **Nur Bild-Prospekte.** Liefert eine Quelle ausschließlich Prospekt-Bilder
  ohne strukturierte Felder, ist sie außerhalb des Scopes. Kein OCR-Raten,
  keine geschätzten Preise -- die Quelle meldet "keine strukturierten Daten"
  und wird übersprungen oder führt (wenn sie die einzige Quelle war) zum
  Abbruch mit Hinweis.
- **Zugang/Schlüssel fehlt oder bricht weg.** Lässt sich der für eine Quelle
  nötige Zugang (z. B. ein aus der Seite gelesener Client-/API-Schlüssel) nicht
  zuverlässig herstellen, ist das ein Abbruchgrund -- kein hartkodierter,
  geratener Schlüssel.

Merksatz: **Den ehrlichen Abbruch bauen, nicht die Krücke.** Ein Abbruch mit
klarer Ursache und Vorschlag ist ein korrektes Ergebnis dieses Skills. Ein
plausibel aussehender, aber unbelegt zusammengeflickter Datensatz ist ein
Fehler -- auch wenn er "funktioniert".

Die Verifikation des Ortsbezugs ist deshalb selbst eine prüfbare Bedingung im
Datenfluss: Der Adapter belegt, *dass* und *womit* er den Ort gefiltert hat
(z. B. zurückgegebener `zipCode` im Request, Händler-/Filiale-Bezug in der
Antwort), und bricht ab, wenn dieser Beleg fehlt.

## Robustheit

- Respektiere robots.txt und vernünftige Request-Raten; cache Ergebnisse pro
  Ort/Woche, statt bei jedem Lauf neu zu ziehen.
- Schreibe Tests für: leeres Quellergebnis (→ kein Auffüllen), nicht
  auflösbarer Ort (→ Abbruch mit Meldung), fehlende Felder (→ als fehlend
  markiert, nicht geraten).

## Was dieser Skill NICHT tut

- Keine Produktgruppen-Zuordnung.
- Keine Bewertung "guter"/"schlechter" Angebote.
- Keine sprachliche Aufbereitung. Nur Beschaffung und Normalisierung.
