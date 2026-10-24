"""Produzione FV oraria da PVGIS (seriescalc) portata a 15 minuti
sul calendario di riferimento, in ora civile italiana (Europe/Rome).

API: https://re.jrc.ec.europa.eu/api/v5_3/seriescalc
Restituisce P [W] per il kWp indicato, ora per ora, in UTC.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .parser import REF_YEAR

PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "pvgis_cache"

# orientamenti PVGIS: aspect 0 = sud, -90 = est, +90 = ovest
ORIENTAMENTI = {
    "Sud": [(0, 1.0)],
    "Est-Ovest (50/50)": [(-90, 0.5), (90, 0.5)],
    "Sud-Est": [(-45, 1.0)],
    "Sud-Ovest": [(45, 1.0)],
}


def _fetch_pvgis(lat, lon, angle, aspect, loss, y0, y1) -> pd.Series:
    """Serie oraria UTC di produzione [kW per kWp]. Cache su disco
    (dati pubblici, nessun dato personale)."""
    params = dict(
        lat=round(lat, 4), lon=round(lon, 4), peakpower=1, loss=loss,
        angle=angle, aspect=aspect, pvcalculation=1, mountingplace="building",
        startyear=y0, endyear=y1, outputformat="json",
    )
    key = hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    f = CACHE_DIR / f"pvgis_{key}.parquet"
    if f.exists():
        return pd.read_parquet(f)["P"]
    r = requests.get(PVGIS_URL, params=params, timeout=60)
    r.raise_for_status()
    rows = r.json()["outputs"]["hourly"]
    df = pd.DataFrame(rows)
    # time "20200101:0010" -> ora UTC; il valore e' la potenza media dell'ora
    t = pd.to_datetime(df["time"], format="%Y%m%d:%H%M", utc=True).dt.floor("h")
    s = pd.Series(df["P"].to_numpy() / 1000.0, index=t, name="P")  # kW/kWp
    s.to_frame().to_parquet(f)
    return s


def _hourly_to_ref_15min(s_utc: pd.Series, year: int) -> np.ndarray:
    """Porta un anno di potenza oraria UTC su 365x96 quarti d'ora in ora
    civile locale (come il contatore). Ritorna kWh/15min per kWp."""
    s = s_utc[s_utc.index.year == year]
    # quarti d'ora: potenza media oraria interpolata tra i centri ora,
    # poi riscalata per conservare l'energia di ogni ora
    centers = s.index + pd.Timedelta(minutes=30)
    q_idx = pd.date_range(s.index[0], s.index[-1] + pd.Timedelta(minutes=45),
                          freq="15min", tz="UTC")
    q_mid = q_idx + pd.Timedelta(minutes=7.5)
    p = np.interp(q_mid.asi8, centers.asi8, s.to_numpy(), left=0, right=0)
    p = np.clip(p, 0, None)
    hours = q_idx.floor("h")
    e = pd.Series(p * 0.25, index=q_idx)
    h_sum = e.groupby(hours).transform("sum").to_numpy()
    target = s.reindex(hours).to_numpy()  # kWh dell'ora (P media * 1h)
    with np.errstate(invalid="ignore", divide="ignore"):
        e = np.where(h_sum > 0, e.to_numpy() * target / h_sum, 0.0)
    loc = q_idx.tz_convert("Europe/Rome")
    df = pd.DataFrame({"e": e, "d": loc.tz_localize(None).normalize(),
                       "slot": loc.hour * 4 + loc.minute // 15})
    df = df[df["d"].dt.year == year]
    df = df[~((df["d"].dt.month == 2) & (df["d"].dt.day == 29))]
    # cambio ora: slot doppi mediati, slot mancanti interpolati
    grid = df.groupby(["d", "slot"])["e"].mean().unstack("slot").reindex(columns=range(96))
    grid = grid.interpolate(axis=1, limit_direction="both").fillna(0)
    if len(grid) != 365:
        grid = grid.reindex(
            pd.date_range(grid.index.min(), periods=365, freq="D")
        ).ffill().bfill()
    return grid.to_numpy().ravel()


def pv_profiles(lat, lon, angle=35, orientamento="Sud", loss=14,
                y0=2014, y1=2023) -> dict[int, pd.Series]:
    """Profili di produzione per 1 kWp, uno per ogni anno meteo PVGIS.
    Ritorna {anno: Series 35040 kWh/15min sul calendario REF_YEAR}."""
    parts = ORIENTAMENTI[orientamento]
    idx = pd.date_range(f"{REF_YEAR}-01-01", periods=365 * 96, freq="15min")
    out = {}
    series = [(_fetch_pvgis(lat, lon, angle, asp, loss, y0, y1), w) for asp, w in parts]
    for y in range(y0, y1 + 1):
        tot = sum(w * _hourly_to_ref_15min(s, y) for s, w in series)
        out[y] = pd.Series(tot, index=idx, name=f"pv_{y}")
    return out


def pick_years(profiles: dict[int, pd.Series]) -> dict[str, int]:
    """Anni con produzione annua minima, mediana e massima."""
    tot = pd.Series({y: s.sum() for y, s in profiles.items()}).sort_values()
    return {"min": int(tot.index[0]),
            "mediana": int(tot.index[len(tot) // 2]),
            "max": int(tot.index[-1])}
