"""Analisi economica a flussi di cassa annuali, con attualizzazione.

Flussi: anno 0 investimento; anni 1..N risparmio in bolletta (con inflazione del
prezzo dell'energia e degrado dei moduli), manutenzione, quote di incentivo,
eventuale sostituzione della batteria.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Finanza:
    prezzo_prelievo: float = 0.28
    valore_immissione: float = 0.09
    costo_fv_kwp: float = 1600.0
    costo_batt_kwh: float = 550.0
    costo_batt_fisso: float = 1500.0
    # incentivo
    incentivo_pct: float = 0.0
    incentivo_rate: int = 1
    massimale_spesa: float | None = None  # € per intervento
    massimale_fv_kwp: float | None = None  # €/kWp ammissibili
    massimale_batt_kwh: float | None = None  # €/kWh ammissibili
    # parametri finanziari
    orizzonte: int = 20
    tasso_sconto: float = 0.03
    inflazione_energia: float = 0.02
    degrado_fv: float = 0.005
    manutenzione_kwp: float = 15.0  # €/kWp/anno
    vita_batteria: int = 15
    sostituzione_frac: float = 0.5  # costo sostituzione / costo batteria di oggi


def investimento(kwp, kwh, f: Finanza):
    c_fv = kwp * f.costo_fv_kwp
    c_b = kwh * f.costo_batt_kwh + f.costo_batt_fisso if kwh > 0 else 0.0
    return c_fv, c_b


def incentivo_totale(kwp, kwh, f: Finanza):
    c_fv, c_b = investimento(kwp, kwh, f)
    if f.massimale_fv_kwp:
        c_fv = min(c_fv, kwp * f.massimale_fv_kwp)
    if f.massimale_batt_kwh and kwh > 0:
        c_b = min(c_b, kwh * f.massimale_batt_kwh)
    amm = c_fv + c_b
    if f.massimale_spesa:
        amm = min(amm, f.massimale_spesa)
    return f.incentivo_pct * amm


def flussi(r: dict, consumo: float, f: Finanza) -> np.ndarray:
    kwp, kwh = r["kwp"], r["kwh"]
    inv = sum(investimento(kwp, kwh, f))
    t = np.arange(1, f.orizzonte + 1)
    risp0 = (consumo - r["prelievo"]) * f.prezzo_prelievo + r["immissione"] * f.valore_immissione
    risp = risp0 * (1 + f.inflazione_energia) ** (t - 1) * (1 - f.degrado_fv) ** (t - 1)
    cf = np.zeros(f.orizzonte + 1)
    cf[0] = -inv
    cf[1:] = risp - f.manutenzione_kwp * kwp
    n = max(1, int(f.incentivo_rate))
    cf[1:n + 1] += incentivo_totale(kwp, kwh, f) / n
    if kwh > 0 and f.vita_batteria < f.orizzonte:
        cf[f.vita_batteria] -= f.sostituzione_frac * kwh * f.costo_batt_kwh
    return cf


def _payback(cum):
    """Primo anno (frazionario) in cui il cumulato torna >= 0."""
    if cum[0] >= 0:
        return 0.0
    idx = np.where(cum >= 0)[0]
    if len(idx) == 0:
        return np.inf
    i = idx[0]
    return float(i - 1 + (-cum[i - 1]) / (cum[i] - cum[i - 1]))


def indicatori(cf: np.ndarray, tasso: float) -> dict:
    disc = cf / (1 + tasso) ** np.arange(len(cf))
    return {
        "investimento": -cf[0],
        "risparmio_primo_anno": cf[1],
        "payback": _payback(np.cumsum(cf)),
        "payback_att": _payback(np.cumsum(disc)),
        "van": disc.sum(),
        "guadagno_nominale": cf.sum(),
    }


def valuta(grid: pd.DataFrame, consumo: float, f: Finanza) -> pd.DataFrame:
    """Aggiunge a ogni configurazione della scansione gli indicatori economici,
    anche per la sola batteria (differenza rispetto al FV senza batteria)."""
    rows, cfs = [], {}
    for g in grid.to_dict("records"):
        cf = flussi(g, consumo, f)
        cfs[(g["kwp"], g["kwh"])] = cf
        rows.append({**g, **indicatori(cf, f.tasso_sconto),
                     "incentivo": incentivo_totale(g["kwp"], g["kwh"], f),
                     "netto": -cf[0] - incentivo_totale(g["kwp"], g["kwh"], f)})
    e = pd.DataFrame(rows)
    pb_b, van_b = [], []
    for g in rows:
        if g["kwh"] > 0 and (g["kwp"], 0.0) in cfs:
            ind = indicatori(cfs[(g["kwp"], g["kwh"])] - cfs[(g["kwp"], 0.0)], f.tasso_sconto)
            pb_b.append(ind["payback_att"])
            van_b.append(ind["van"])
        else:
            pb_b.append(np.nan)
            van_b.append(np.nan)
    e["payback_att_batteria"] = pb_b
    e["van_batteria"] = van_b
    return e


OBIETTIVI = {
    "rientro_rapido": "Rientrare il prima possibile",
    "guadagno": "Il massimo guadagno nel tempo",
    "rientro_entro": "Rientrare entro un certo numero di anni, con la massima autonomia",
    "autonomia": "Raggiungere una certa autonomia, spendendo il meno possibile",
}


def scegli(e: pd.DataFrame, obiettivo: str, valore: float | None = None) -> tuple[pd.Series, str | None]:
    """Sceglie la configurazione in base all'obiettivo. Ritorna (riga, avviso)."""
    avviso = None
    if obiettivo == "rientro_rapido":
        # tra le configurazioni che rientrano entro 6 mesi dalla piu' rapida, la piu' autonoma
        ok = e[e["payback_att"] <= e["payback_att"].min() + 0.5]
        r = ok.sort_values(["autosufficienza", "netto"], ascending=[False, True]).iloc[0]
    elif obiettivo == "guadagno":
        # tra quelle con almeno il 95% del guadagno massimo, la meno costosa:
        # evita di sovradimensionare per guadagni marginali
        vmax = e["van"].max()
        ok = e[e["van"] >= (0.95 * vmax if vmax > 0 else vmax)]
        r = ok.sort_values("netto").iloc[0]
    elif obiettivo == "rientro_entro":
        ok = e[e["payback_att"] <= valore]
        if ok.empty:
            r = e.sort_values("payback_att").iloc[0]
            avviso = (f"Nessuna configurazione rientra in {valore:g} anni con questi costi: "
                      f"la più rapida rientra in {r['payback_att']:.0f} anni.")
        else:
            best = ok["autosufficienza"].max()
            # a parità di autonomia (entro 1 punto) la meno costosa
            r = ok[ok["autosufficienza"] >= best - 0.01].sort_values("netto").iloc[0]
    elif obiettivo == "autonomia":
        ok = e[e["autosufficienza"] >= valore]
        if ok.empty:
            r = e.sort_values(["autosufficienza", "netto"], ascending=[False, True]).iloc[0]
            avviso = (f"Con lo spazio disponibile e una batteria giornaliera non si arriva al "
                      f"{valore:.0%}: il massimo è circa il {r['autosufficienza']:.0%}. "
                      "D'inverno il sole non basta e la batteria non può spostare energia "
                      "dall'estate all'inverno.")
        else:
            r = ok.sort_values("netto").iloc[0]
    else:
        raise ValueError(obiettivo)
    return r, avviso
