"""Ricerca di un comune per nome: Nominatim (OSM), con ripiego su Open-Meteo Geocoding.

Si interroga solo quando l'utente conferma la ricerca (Invio), mai durante la digitazione.
"""
import requests

UA = "climaction-calcolatore-fv/1.0 (https://climaction.it)"
TIMEOUT = 8


def _nominatim(q: str, n: int) -> list[dict]:
    r = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": q, "countrycodes": "it", "format": "jsonv2", "addressdetails": 1,
                "limit": n, "accept-language": "it"},
        headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for it in r.json():
        a = it.get("address", {})
        nome = (a.get("city") or a.get("town") or a.get("village") or a.get("municipality")
                or a.get("hamlet") or it.get("name") or q)
        prov = a.get("county") or a.get("state_district") or ""
        out.append({"nome": nome, "provincia": prov, "regione": a.get("state", ""),
                    "lat": float(it["lat"]), "lon": float(it["lon"])})
    return out


def _openmeteo(q: str, n: int) -> list[dict]:
    r = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": q, "count": n, "language": "it", "format": "json", "countryCode": "IT"},
        headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    return [{"nome": it["name"], "provincia": it.get("admin2", ""), "regione": it.get("admin1", ""),
             "lat": float(it["latitude"]), "lon": float(it["longitude"])}
            for it in r.json().get("results", [])]


def cerca(q: str, n: int = 5) -> list[dict]:
    """Restituisce fino a n luoghi; solleva RuntimeError se nessun servizio risponde."""
    q = q.strip()
    if len(q) < 2:
        return []
    errori = []
    for f in (_nominatim, _openmeteo):
        try:
            ris = f(q, n)
            if ris:
                return ris
        except Exception as e:  # noqa: BLE001
            errori.append(f"{f.__name__}: {e}")
    if errori:
        raise RuntimeError("; ".join(errori))
    return []


def etichetta(p: dict) -> str:
    extra = ", ".join(x for x in (p["provincia"], p["regione"]) if x)
    return f"{p['nome']} ({extra})" if extra else p["nome"]
