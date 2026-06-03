"""Konfiguration -- bewusst getrennt von der Logik.

Produktgruppen, Quellenliste und Orts-Auflösung leben hier, damit das Team sie
ändern kann, ohne Kern- oder Prompt-Code anzufassen.
"""

from __future__ import annotations

# --- Kategorisierung: geschlossene Liste (siehe SKILL angebote-kategorisieren) ---

PRODUKTGRUPPEN: tuple[str, ...] = (
    "Obst & Gemüse",
    "Fleisch & Wurst",
    "Fisch",
    "Molkereiprodukte & Eier",
    "Brot & Backwaren",
    "Grundnahrungsmittel (Nudeln, Reis, Mehl, Konserven)",
    "Süßwaren & Snacks",
    "Getränke (alkoholfrei)",
    "Alkoholische Getränke",
    "Tiefkühl",
    "Drogerie & Haushalt",
    "Non-Food (Kleidung, Spielzeug, Garten, Technik)",
    "Sonstiges",
)

# Auffanggruppe, wenn ein Artikel in keine passt ODER das Modell eine Gruppe
# außerhalb der Liste liefert. Muss in PRODUKTGRUPPEN enthalten sein.
FALLBACK_GRUPPE: str = "Sonstiges"

# --- Fetch: bekannte Abdeckungslöcher, die ehrlich ausgewiesen werden ---

# Sentinel-Werte der Quelle für "kein Wert". marktguru setzt z. B. einen
# Platzhalter-Markennamen, wenn keine Marke vorliegt -- der darf NICHT als echte
# Marke durchgereicht werden, sonst behaupten wir einen Beleg, den es nicht gibt.
MARKE_SENTINELS: tuple[str, ...] = ("thisisnobrand123",)

# Hinweis Abdeckung: Welche Händler tatsächlich enthalten sind, ergibt sich aus
# den abgerufenen Daten (datengetrieben), nicht aus einer hartkodierten Annahme.
# Eine pauschale "Discounter X fehlt"-Behauptung wäre unbelegt -- Discounter wie
# Aldi/Lidl können je nach Quelle/Ort sehr wohl enthalten sein.

# Seedbegriffe für query-orientierte Quellen (z. B. marktguru): deren API hat
# kein "alle Angebote"-Browse (leeres q -> 0 Treffer), nur Suche. Diese Liste
# spannt die Abdeckung auf. Sie ist BEWUSST endlich und damit unvollständig --
# was sie nicht trifft, fehlt ehrlich, statt vorgetäuscht zu werden.
SUCHBEGRIFFE: tuple[str, ...] = (
    "Obst", "Gemüse", "Apfel", "Banane", "Tomate", "Kartoffel", "Salat",
    "Fleisch", "Hähnchen", "Hackfleisch", "Schnitzel", "Wurst", "Schinken",
    "Fisch", "Lachs",
    "Milch", "Butter", "Käse", "Joghurt", "Quark", "Eier", "Sahne",
    "Brot", "Brötchen", "Toast",
    "Nudeln", "Reis", "Mehl", "Zucker", "Öl", "Konserve",
    "Schokolade", "Süßigkeiten", "Chips", "Kekse",
    "Wasser", "Saft", "Cola", "Kaffee", "Tee",
    "Bier", "Wein", "Sekt",
    "Pizza", "Eis", "Tiefkühl",
    "Waschmittel", "Shampoo", "Toilettenpapier", "Zahnpasta",
)

# --- Orts-Auflösung (deterministisch, KEIN LLM) ---
#
# 5-stellige Eingaben gelten direkt als PLZ. Ortsnamen werden NUR über diese
# bewusst kleine, kuratierte Auswahl großer Städte aufgelöst. Ein unbekannter
# Ortsname führt zum ehrlichen Abbruch (Regel 4) mit dem Vorschlag, eine PLZ
# anzugeben -- es wird KEINE PLZ geraten.
ORTSNAME_PLZ: dict[str, str] = {
    "berlin": "10115",
    "hamburg": "20095",
    "münchen": "80331",
    "muenchen": "80331",
    "köln": "50667",
    "koeln": "50667",
    "frankfurt": "60311",
    "frankfurt am main": "60311",
    "stuttgart": "70173",
    "düsseldorf": "40213",
    "duesseldorf": "40213",
    "leipzig": "04109",
    "dortmund": "44135",
    "essen": "45127",
    "bremen": "28195",
    "dresden": "01067",
    "hannover": "30159",
    "nürnberg": "90402",
    "nuernberg": "90402",
}
