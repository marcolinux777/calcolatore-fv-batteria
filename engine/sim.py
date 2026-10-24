"""Simulazione cronologica a 15 minuti di FV + batteria e scansione kWp x kWh.

Strategia di batteria: autoconsumo puro (carica col surplus FV, scarica
sul deficit), nessuna carica da rete.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

try:  # numba opzionale: ~50x piu' veloce sulla scansione
    from numba import njit
except ImportError:  # pragma: no cover
    def njit(*a, **k):
        def deco(f):
            return f
        return deco(a[0]) if a and callable(a[0]) else deco

DT = 0.25  # h


@dataclass
class Battery:
    capacita_kwh: float = 10.0  # nominale
    dod: float = 0.90  # profondita' di scarica utile
    eta_rt: float = 0.92  # rendimento round-trip
    c_rate: float = 0.5  # potenza max = c_rate * capacita' nominale
    p_min_kw: float = 2.5  # potenza minima dell'inverter batteria

    @property
    def utile(self):
        return self.capacita_kwh * self.dod

    @property
    def potenza_kw(self):
        return 0.0 if self.capacita_kwh <= 0 else max(self.c_rate * self.capacita_kwh, self.p_min_kw)


@njit(cache=True)
def _dispatch(load, pv, cap, p_max, eta_rt, dt, lim):
    n = load.shape[0]
    eta = np.sqrt(eta_rt)
    soc = np.empty(n)
    imp = np.empty(n)
    exp = np.empty(n)
    ch = np.empty(n)
    dis = np.empty(n)
    cut = np.zeros(n)
    s = 0.5 * cap
    e_max = p_max * dt
    for i in range(n):
        net = pv[i] - load[i]
        c = 0.0
        d = 0.0
        if net > 0:
            c = min(net, e_max, (cap - s) / eta) if cap > 0 else 0.0
            s += c * eta
            exp[i] = net - c
            if lim > 0 and exp[i] > lim * dt:  # limite di immissione
                cut[i] = exp[i] - lim * dt
                exp[i] = lim * dt
            imp[i] = 0.0
        else:
            need = -net
            d = min(need, e_max, s * eta) if cap > 0 else 0.0
            s -= d / eta
            imp[i] = need - d
            exp[i] = 0.0
        ch[i] = c
        dis[i] = d
        soc[i] = s
    return soc, imp, exp, ch, dis, cut


def simulate(load: pd.Series, pv1: pd.Series, kwp: float, batt: Battery,
             detail: bool = False, lim_kw: float = 0.0):
    """load, pv1: kWh/15min (pv1 per 1 kWp). Ritorna dict di indicatori
    (e, se detail, DataFrame a 15 min)."""
    L = load.to_numpy(dtype=np.float64)
    P = pv1.to_numpy(dtype=np.float64) * kwp
    cap = batt.utile
    # due passate: la prima porta lo SOC iniziale a regime
    soc, imp, exp, ch, dis, cut = _dispatch(L, P, cap, batt.potenza_kw, batt.eta_rt, DT, lim_kw)
    soc, imp, exp, ch, dis, cut = _dispatch(L, P, cap, batt.potenza_kw, batt.eta_rt, DT, lim_kw)

    tot_L, tot_P = L.sum(), P.sum()
    autoc = tot_P - exp.sum() - cut.sum()
    r = {
        "kwp": kwp,
        "kwh": batt.capacita_kwh,
        "carico": tot_L,
        "produzione": tot_P,
        "prelievo": imp.sum(),
        "immissione": exp.sum(),
        "autoconsumo_kwh": autoc,
        "tagliata": cut.sum(),
        "autoconsumo": autoc / tot_P if tot_P > 0 else 0.0,
        "autosufficienza": 1 - imp.sum() / tot_L,
        "cicli": dis.sum() / cap if cap > 0 else 0.0,
    }
    if cap > 0:
        sd = soc.reshape(365, 96)
        r["giorni_piena"] = int((sd.max(axis=1) >= 0.98 * cap).sum())
        r["giorni_vuota"] = int((sd.min(axis=1) <= 0.02 * cap).sum())
    else:
        r["giorni_piena"] = r["giorni_vuota"] = 0
    if detail:
        df = pd.DataFrame({"carico": L, "fv": P, "prelievo": imp, "immissione": exp,
                           "carica": ch, "scarica": dis, "soc": soc}, index=load.index)
        df["tagliata"] = cut
        df["fv_diretto"] = df["fv"] - df["immissione"] - df["carica"] - df["tagliata"]
        return r, df
    return r


def scan(load, pv1, kwp_list, kwh_list, batt_template: Battery, lim_kw: float = 0.0) -> pd.DataFrame:
    rows = []
    for kwp in kwp_list:
        for kwh in kwh_list:
            b = Battery(kwh, batt_template.dod, batt_template.eta_rt,
                        batt_template.c_rate, batt_template.p_min_kw)
            rows.append(simulate(load, pv1, kwp, b, lim_kw=lim_kw))
    return pd.DataFrame(rows)


def knee(df_scan: pd.DataFrame, soglia_pp_per_kwh: float = 1.5) -> pd.DataFrame:
    """Per ogni kWp, la capacita' oltre la quale ogni kWh di batteria in piu'
    aggiunge meno di `soglia` punti percentuali di autosufficienza."""
    out = []
    for kwp, g in df_scan.groupby("kwp"):
        g = g.sort_values("kwh")
        x, y = g["kwh"].to_numpy(), g["autosufficienza"].to_numpy() * 100
        marg = np.diff(y) / np.diff(x)
        k = x[0]
        for i, m in enumerate(marg):
            if m >= soglia_pp_per_kwh:
                k = x[i + 1]
            else:
                break
        row = g[g["kwh"] == k].iloc[0]
        out.append({"kwp": kwp, "kwh_ginocchio": k,
                    "autosufficienza": row["autosufficienza"],
                    "autoconsumo": row["autoconsumo"],
                    "cicli": row["cicli"]})
    return pd.DataFrame(out)
