"""marktguru-Adapter -- erste echte Quelle. REIN DETERMINISTISCH, kein LLM.

Die API ist öffentlich dokumentiert nachvollziehbar (Reverse-Engineering durch
mehrere Community-Projekte):

  Basis      : https://api.marktguru.de/api/v1
  Endpoint   : offers/search
  Parameter  : as=web, q=<suche>, zipCode=<PLZ>, limit, offset
  Header     : x-apikey, x-clientkey  -- werden aus dem in der Startseite
               eingebetteten <script type="application/json">-Config-Block gelesen
               (Felder apiKey / clientKey), oder per ENV überschrieben.
  Felder      : offer.product.name, offer.brand.name, offer.price,
               offer.advertisers[].name, offer.validityDates[].from / .to,
               offer.volume + offer.quantity + offer.unit.name  -> Packungsmenge,
               offer.referencePrice (numerisch, je unit.name) -> Grundpreis.

Anmerkung Ortsbezug/Abdeckung: offers/search ist QUERY-orientiert -- ein leeres
q liefert 0 Treffer, kein "alle Angebote"-Browse. Eine vollständige
ortsweite Aufzählung gibt die API nicht her; der Adapter fragt deshalb die in
SUCHBEGRIFFE hinterlegten Kategorie-Seedbegriffe ab und meldet diese
Teilabdeckung ehrlich, statt Vollständigkeit vorzutäuschen.

Ortsbezug: `zipCode` ist ein EXPLIZITER Query-Parameter -- der Ortsfilter steckt
also nicht in Session/Cookie. Der Adapter belegt den Filter über den
mitgesendeten `zipCode` und bricht ab (Regel 4), wenn er ihn nicht herstellen
kann. Lässt sich der Zugang (Schlüssel) nicht herstellen -> Abbruch, kein
geratener Schlüssel.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from urllib.robotparser import RobotFileParser

from ..fehler import AbbruchFehler
from ..modell import Angebot
from .basis import Ort

_HOMEPAGE = "https://www.marktguru.de"
_API_BASIS = "https://api.marktguru.de/api/v1"
_OFFERS_SEARCH = f"{_API_BASIS}/offers/search"
_USER_AGENT = "angebote-uebersicht/0.1 (+kontaktloser, robots-treuer Aggregator)"
_CONFIG_RE = re.compile(
    r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', re.DOTALL
)


class MarktguruAdapter:
    """Adapter für marktguru.de. Erfüllt das QuelleAdapter-Protokoll."""

    name = "marktguru"

    def __init__(
        self,
        *,
        suchbegriffe: tuple[str, ...] | None = None,
        limit: int = 100,
        cache_dir: str | Path | None = None,
        session=None,
    ) -> None:
        from ..config import SUCHBEGRIFFE

        self.suchbegriffe = tuple(suchbegriffe) if suchbegriffe is not None else SUCHBEGRIFFE
        self.limit = limit
        self.cache_dir = Path(cache_dir) if cache_dir else Path(".cache/marktguru")
        self._session = session  # für Tests injizierbar
        self._apikey: str | None = None
        self._clientkey: str | None = None
        # Ehrliche Abdeckungs-Notiz, vom Orchestrator eingesammelt:
        self.abdeckungshinweis = (
            f"marktguru: query-basierte Teilabdeckung über {len(self.suchbegriffe)} "
            "Seedbegriffe -- keine vollständige Aufzählung aller Angebote."
        )

    # -- QuelleAdapter ----------------------------------------------------

    def deckt_ab(self, ort: Ort) -> bool:
        # marktguru filtert bundesweit über PLZ. Eine 5-stellige PLZ gilt als
        # abgedeckt; ob konkret Angebote vorliegen, entscheidet erst `hole`.
        return bool(ort.plz) and ort.plz.isdigit() and len(ort.plz) == 5

    def hole(self, ort: Ort) -> list[Angebot]:
        if not self.deckt_ab(ort):
            raise AbbruchFehler(
                schwelle="marktguru: PLZ-Filter",
                ursache=f"'{ort.plz}' ist keine gültige 5-stellige PLZ",
                vorschlag="eine 5-stellige PLZ angeben (z. B. 60487)",
            )

        roh, abgerufen_am = self._hole_roh(ort)
        angebote = self._parse(roh, ort, abgerufen_am)

        # Ortsbezug verifizieren: Es gab Treffer, aber der Filter ist nur dann
        # belegt, wenn wir ihn auch wirklich mitgesendet haben (siehe quelle).
        # Trefferzahl 0 ist KEIN Fehler -> leeres Ergebnis (kein Auffüllen).
        return angebote

    # -- intern -----------------------------------------------------------

    def _sess(self):
        if self._session is None:
            import requests  # lokal, damit der Fetch-Teil ohne Netz importierbar bleibt

            self._session = requests.Session()
            self._session.headers.update({"User-Agent": _USER_AGENT})
        return self._session

    def _robots_pruefen(self, url: str) -> tuple[bool, str]:
        """Prüft robots.txt. Gibt (erlaubt, ehrliche_ursache_falls_nicht) zurück.

        robots.txt wird über DENSELBEN Transport wie der eigentliche Abruf
        geholt (requests, certifi-gestützt) -- damit ein erfolgreicher Abruf
        und ein erfolgreicher robots-Check dieselbe Vertrauensbasis haben.

        Wichtig für die Ehrlichkeit des Abbruchs: 'nicht prüfbar' (Netz-/SSL-/
        HTTP-Fehler) ist NICHT dasselbe wie 'durch robots.txt untersagt'. Beide
        führen konservativ zum Nicht-Abruf, aber die genannte Ursache muss
        zutreffen -- es wird keine Sperre behauptet, die nicht belegt ist.
        Fehlt robots.txt (404), gilt der Pfad als erlaubt.
        """
        from urllib.parse import urlsplit

        teile = urlsplit(url)
        robots_url = f"{teile.scheme}://{teile.netloc}/robots.txt"
        try:
            antwort = self._sess().get(robots_url, timeout=20)
        except Exception as e:
            return False, f"robots.txt nicht prüfbar ({robots_url}: {e})"
        if antwort.status_code == 404:
            return True, ""
        if antwort.status_code != 200:
            return False, f"robots.txt nicht prüfbar ({robots_url}: HTTP {antwort.status_code})"
        rp = RobotFileParser()
        rp.parse(antwort.text.splitlines())
        if rp.can_fetch(_USER_AGENT, url):
            return True, ""
        return False, f"durch robots.txt untersagt ({robots_url})"

    def _schluessel(self) -> tuple[str, str]:
        if self._apikey and self._clientkey:
            return self._apikey, self._clientkey

        env_api = os.environ.get("MARKTGURU_APIKEY")
        env_client = os.environ.get("MARKTGURU_CLIENTKEY")
        if env_api and env_client:
            self._apikey, self._clientkey = env_api, env_client
            return self._apikey, self._clientkey

        erlaubt, grund = self._robots_pruefen(_HOMEPAGE)
        if not erlaubt:
            raise AbbruchFehler(
                schwelle="marktguru: Startseite nicht abrufbar",
                ursache=grund,
                vorschlag="Schlüssel per ENV MARKTGURU_APIKEY/MARKTGURU_CLIENTKEY setzen",
            )

        try:
            antwort = self._sess().get(_HOMEPAGE, timeout=20)
            antwort.raise_for_status()
            html = antwort.text
        except Exception as e:  # Netz-/HTTP-Fehler
            raise AbbruchFehler(
                schwelle="marktguru: Zugang",
                ursache=f"Startseite nicht abrufbar ({e})",
                vorschlag="Netzverbindung prüfen oder Schlüssel per ENV setzen",
            ) from e

        api, client = self._schluessel_aus_html(html)
        if not api or not client:
            raise AbbruchFehler(
                schwelle="marktguru: Zugang",
                ursache="apiKey/clientKey nicht im Config-Block der Startseite gefunden "
                "(Seitenstruktur geändert?)",
                vorschlag="Schlüssel per ENV MARKTGURU_APIKEY/MARKTGURU_CLIENTKEY setzen",
            )
        self._apikey, self._clientkey = api, client
        return api, client

    @staticmethod
    def _schluessel_aus_html(html: str) -> tuple[str | None, str | None]:
        for block in _CONFIG_RE.findall(html):
            try:
                cfg = json.loads(block)
            except json.JSONDecodeError:
                continue
            api, client = _suche_keys(cfg)
            if api and client:
                return api, client
        return None, None

    def _cache_pfad(self, ort: Ort, abgerufen_am: datetime) -> Path:
        jahr, woche, _ = abgerufen_am.isocalendar()
        return self.cache_dir / f"{ort.plz}_{jahr}-W{woche:02d}.json"

    def _hole_roh(self, ort: Ort) -> tuple[list[dict], datetime]:
        """Aggregiert die rohen Offer-Objekte über alle Seedbegriffe (dedupliziert).

        Cache pro PLZ/Kalenderwoche; bei Treffer wird nicht erneut gezogen.
        Ein einzelner Suchbegriff ohne Treffer ist KEIN Fehler -- nur ein
        leerer Beitrag. Bricht hingegen der Zugang/HTTP, gilt Regel 4.
        """
        jetzt = datetime.now()
        treffer = self._cache_pfad(ort, jetzt)
        if treffer.exists():
            gespeichert = json.loads(treffer.read_text(encoding="utf-8"))
            return gespeichert["results"], datetime.fromisoformat(
                gespeichert["abgerufen_am"]
            )

        erlaubt, grund = self._robots_pruefen(_OFFERS_SEARCH)
        if not erlaubt:
            raise AbbruchFehler(
                schwelle="marktguru: API nicht abrufbar",
                ursache=grund,
                vorschlag="andere Quelle wählen, Netz/Zertifikate prüfen oder Betreiber kontaktieren",
            )

        api, client = self._schluessel()
        headers = {"x-apikey": api, "x-clientkey": client}
        gesehen: set[str] = set()
        aggregiert: list[dict] = []
        for begriff in self.suchbegriffe:
            for offer in self._suche_eine(begriff, ort, headers):
                oid = str(offer.get("id") or "")
                schluessel = oid or json.dumps(offer, sort_keys=True)[:120]
                if schluessel in gesehen:
                    continue
                gesehen.add(schluessel)
                aggregiert.append(offer)

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        treffer.write_text(
            json.dumps({"abgerufen_am": jetzt.isoformat(), "results": aggregiert}),
            encoding="utf-8",
        )
        return aggregiert, jetzt

    def _suche_eine(self, begriff: str, ort: Ort, headers: dict) -> list[dict]:
        params = {
            "as": "web",
            "q": begriff,
            "limit": str(self.limit),
            "offset": "0",
            "zipCode": ort.plz,  # <-- belegter Ortsfilter
        }
        try:
            antwort = self._sess().get(
                _OFFERS_SEARCH, params=params, headers=headers, timeout=30
            )
            antwort.raise_for_status()
            daten = antwort.json()
        except Exception as e:
            raise AbbruchFehler(
                schwelle="marktguru: Abruf",
                ursache=f"offers/search fehlgeschlagen für '{begriff}' ({e})",
                vorschlag="später erneut versuchen, PLZ prüfen, ggf. Schlüssel erneuern",
            ) from e

        results = daten.get("results")
        if results is None:
            raise AbbruchFehler(
                schwelle="marktguru: Antwortform",
                ursache="Antwort enthält kein 'results' (API-Form geändert?)",
                vorschlag="Parser an neue Antwortstruktur anpassen",
            )
        return results

    def _parse(
        self, results: list[dict], ort: Ort, abgerufen_am: datetime
    ) -> list[Angebot]:
        angebote: list[Angebot] = []
        for eintrag in results:
            offer = eintrag.get("offer", eintrag)  # je nach Antwortform
            titel = _pfad(offer, "product", "name")
            if not titel:
                # Ohne belegten Titel ist der Eintrag nicht verwertbar -> weglassen,
                # NICHT mit Platzhalter füllen.
                continue
            haendler = _erster_name(offer.get("advertisers")) or "unbekannt (marktguru)"
            offer_id = str(offer.get("id") or "")
            einheit = _pfad(offer, "unit", "name")
            angebote.append(
                Angebot(
                    titel=titel,
                    marke=_marke(_pfad(offer, "brand", "name")),
                    preis=_als_float(offer.get("price")),
                    grundpreis=_grundpreis(offer.get("referencePrice"), einheit),
                    menge=_menge(offer.get("quantity"), offer.get("volume"), einheit),
                    gueltig_von=_erstes_datum(offer.get("validityDates"), "from"),
                    gueltig_bis=_erstes_datum(offer.get("validityDates"), "to"),
                    haendler=haendler,
                    # quelle belegt zugleich den Ortsfilter (zipCode):
                    quelle=f"marktguru:offers/search?zipCode={ort.plz}#offer={offer_id}",
                    abgerufen_am=abgerufen_am,
                )
            )
        return angebote


# --- kleine, reine Hilfsfunktionen (keine Daten-Reparatur, nur Auslesen) -----


def _suche_keys(obj) -> tuple[str | None, str | None]:
    """Findet apiKey/clientKey rekursiv im Config-Objekt der Startseite."""
    api = client = None
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = k.lower()
            if kl == "apikey" and isinstance(v, str):
                api = v
            elif kl == "clientkey" and isinstance(v, str):
                client = v
            else:
                a, c = _suche_keys(v)
                api = api or a
                client = client or c
    elif isinstance(obj, list):
        for el in obj:
            a, c = _suche_keys(el)
            api = api or a
            client = client or c
    return api, client


def _pfad(obj: dict, *schluessel: str) -> str | None:
    cur = obj
    for s in schluessel:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(s)
    if isinstance(cur, str) and cur.strip():
        return cur
    return None


def _marke(wert: str | None) -> str | None:
    """Filtert den Sentinel der Quelle für 'keine Marke' heraus."""
    from ..config import MARKE_SENTINELS

    if wert is None or wert in MARKE_SENTINELS:
        return None
    return wert


def _erster_name(liste) -> str | None:
    if isinstance(liste, list):
        for el in liste:
            if isinstance(el, dict) and isinstance(el.get("name"), str):
                return el["name"]
    return None


def _als_float(wert) -> float | None:
    if isinstance(wert, (int, float)):
        return float(wert)
    return None  # nicht eindeutig -> fehlend, NICHT geraten


def _zahl(wert) -> str | None:
    """Formatiert eine Zahl ohne überflüssige Nullen, mit Komma. 0.25 -> '0,25'."""
    if not isinstance(wert, (int, float)):
        return None
    text = f"{wert:.3f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _grundpreis(wert, einheit: str | None) -> str | None:
    """Grundpreis aus belegten Feldern komponiert -- nichts umgerechnet/erfunden.

    marktguru liefert referencePrice numerisch (Preis je `unit.name`). Aus den
    zwei belegten Feldern wird eine lesbare, aber unveränderte Darstellung.
    """
    if isinstance(wert, (int, float)) and einheit:
        return f"{wert:.2f} €/{einheit}".replace(".", ",")
    if isinstance(wert, str) and wert.strip():
        return wert  # Falls eine Quelle es doch als String liefert: roh.
    return None


def _menge(quantity, volume, einheit: str | None) -> str | None:
    """Packungsmenge aus quantity × volume + Einheit -- belegt zusammengesetzt."""
    vol = _zahl(volume)
    if not vol or not einheit:
        return None
    if isinstance(quantity, (int, float)) and quantity and quantity != 1:
        return f"{_zahl(quantity)} × {vol} {einheit}"
    return f"{vol} {einheit}"


def _erstes_datum(liste, feld: str) -> date | None:
    if isinstance(liste, list):
        for el in liste:
            if isinstance(el, dict) and el.get(feld):
                return _parse_datum(el[feld])
    return None


def _parse_datum(roh) -> date | None:
    """Gültigkeits-Datum aus ISO-Zeitstempel.

    Zeitzonen-korrekt: marktguru liefert UTC ('...22:00:00Z'). Für einen
    Einkäufer in Deutschland zählt das LOKALE Datum -- sonst entsteht ein
    Off-by-one (22:00Z = 00:00 lokal am Folgetag). Daher Umrechnung nach
    Europe/Berlin, bevor das Datum genommen wird.
    """
    if not isinstance(roh, str):
        return None
    text = roh.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None  # nicht parsebar -> fehlend, nicht geraten
    if dt.tzinfo is not None:
        try:
            from zoneinfo import ZoneInfo

            dt = dt.astimezone(ZoneInfo("Europe/Berlin"))
        except Exception:
            pass  # ohne tz-Daten: belegtes UTC-Datum statt Abbruch
    return dt.date()
