"""Parser del CSV quartorario scaricato dal Portale Consumi ARERA.

Formato atteso (separatore ';'):
pod;data_lettura;...;annomese_riferimento;ea1..ea96;er1..er96
- una riga per giorno, data GG/MM/AAAA
- ea1..ea96 = energia attiva prelevata [kWh] per quarto d'ora (00:00-00:15 ... 23:45-24:00)
- er1..er96 = energia reattiva (ignorata)

Il risultato e' un "anno tipo" di 365 x 96 quarti d'ora sul calendario di
riferimento REF_YEAR (non bisestile), in ora civile locale, allineabile
alla produzione PVGIS.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

REF_YEAR = 2023  # anno non bisestile usato solo come calendario
EA_COLS = [f"ea{i}" for i in range(1, 97)]


@dataclass
class LoadReport:
    pod: str
    righe_file: int
    duplicati_rimossi: int
    giorni_validi: int
    finestra_inizio: pd.Timestamp
    finestra_fine: pd.Timestamp
    giorni_mancanti: list = field(default_factory=list)
    kwh_misurati: float = 0.0
    kwh_anno_tipo: float = 0.0
    avvisi: list = field(default_factory=list)


def read_portale_csv(src) -> pd.DataFrame:
    """Legge il CSV (path, bytes o file-like) e restituisce un DataFrame
    giornaliero 96 colonne, indicizzato per data, senza duplicati."""
    if isinstance(src, (bytes, bytearray)):
        src = io.BytesIO(src)
    df = pd.read_csv(src, sep=";", dtype={"pod": str})
    missing = [c for c in ["data_lettura", *EA_COLS] if c not in df.columns]
    if missing:
        raise ValueError(
            "Il file non sembra un export quartorario del Portale Consumi: "
            f"mancano le colonne {missing[:5]}..."
        )
    df = df.copy()
    df["data"] = pd.to_datetime(df["data_lettura"], format="%d/%m/%Y")
    for c in EA_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def build_load_year(src, days: int = 365) -> tuple[pd.Series, pd.DataFrame, LoadReport]:
    """Costruisce l'anno tipo di carico.

    Restituisce:
      load  : Series di 35040 valori [kWh/15min] indicizzata sul calendario REF_YEAR
      daily : DataFrame giornaliero (data reale) dei dati misurati, 96 colonne
      report: LoadReport con qualita' del dato
    """
    raw = read_portale_csv(src)
    n_raw = len(raw)
    pod = str(raw["pod"].iloc[0]) if "pod" in raw else "?"
    avvisi = []
    if "pod" in raw and raw["pod"].nunique() > 1:
        avvisi.append("Il file contiene piu' POD: uso solo il primo.")
        raw = raw[raw["pod"] == pod]

    # duplicati: stessa data. Se i valori differiscono tengo l'ultima ricezione.
    sort_cols = ["data"] + (["data_ricezione"] if "data_ricezione" in raw else [])
    raw = raw.sort_values(sort_cols)
    n_conflitti = raw.drop_duplicates(["data", *EA_COLS]).duplicated("data").sum()
    if n_conflitti:
        avvisi.append(f"{n_conflitti} date con letture diverse: tenuta l'ultima ricevuta.")
    daily = raw.drop_duplicates("data", keep="last").set_index("data")[EA_COLS]
    daily = daily[daily.notna().sum(axis=1) >= 90]  # scarto giorni quasi vuoti
    daily = daily.interpolate(axis=1, limit_direction="both")
    dup = n_raw - len(daily)

    # finestra: ultimi `days` giorni fino all'ultima data disponibile
    end = daily.index.max()
    start = end - pd.Timedelta(days=days - 1)
    win = daily.loc[start:end]
    all_days = pd.date_range(start, end, freq="D")
    missing = all_days.difference(win.index)
    if len(win) < 0.75 * days:
        avvisi.append(
            f"Solo {len(win)} giorni negli ultimi {days}: i risultati sono poco affidabili."
        )

    # riempimento giorni mancanti: media dei giorni dello stesso tipo
    # (feriale / sabato / domenica) entro +-15 giorni, poi +-45.
    def daytype(ts):
        return 0 if ts.weekday() < 5 else ts.weekday() - 4  # 0 fer, 1 sab, 2 dom

    win_types = np.array([daytype(t) for t in win.index])
    filled = {}
    for d in missing:
        prof = None
        for radius in (15, 45, 400):
            sel = (np.abs((win.index - d).days) <= radius) & (win_types == daytype(d))
            if sel.sum() >= 2:
                prof = win[sel].mean()
                break
        if prof is None:
            prof = win.mean()
        filled[d] = prof
    if filled:
        win = pd.concat([win, pd.DataFrame(filled).T]).sort_index()

    # mappatura sul calendario di riferimento (mese-giorno), 29/02 scartato
    win = win[~((win.index.month == 2) & (win.index.day == 29))]
    ref_dates = pd.to_datetime(
        {"year": REF_YEAR, "month": win.index.month, "day": win.index.day}
    )
    win.index = pd.DatetimeIndex(ref_dates)
    win = win.groupby(level=0).mean().reindex(
        pd.date_range(f"{REF_YEAR}-01-01", f"{REF_YEAR}-12-31", freq="D")
    )
    win = win.interpolate(axis=0, limit_direction="both")

    idx = pd.date_range(f"{REF_YEAR}-01-01", periods=365 * 96, freq="15min")
    load = pd.Series(win.to_numpy().ravel(), index=idx, name="load_kwh")

    rep = LoadReport(
        pod=pod,
        righe_file=n_raw,
        duplicati_rimossi=int(dup),
        giorni_validi=int(len(daily.loc[start:end])),
        finestra_inizio=start,
        finestra_fine=end,
        giorni_mancanti=[d.date() for d in missing],
        kwh_misurati=float(daily.loc[start:end].to_numpy().sum()),
        kwh_anno_tipo=float(load.sum()),
        avvisi=avvisi,
    )
    return load, daily, rep


def missing_ranges(days: list) -> list[tuple]:
    """Raggruppa una lista di date mancanti in intervalli continui."""
    if not days:
        return []
    days = sorted(days)
    out, a, b = [], days[0], days[0]
    for d in days[1:]:
        if (d - b).days == 1:
            b = d
        else:
            out.append((a, b))
            a = b = d
    out.append((a, b))
    return out
