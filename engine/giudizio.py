"""Giudizio qualitativo su un dimensionamento proposto da un installatore.

Nessuna valutazione economica: il contenuto dei preventivi non e' noto.
Il giudizio si basa su grandezze fisiche (produzione/consumo, ginocchio
della curva di autosufficienza, giorni in cui la batteria si riempie).
"""
from __future__ import annotations

import pandas as pd

from . import sim


def _n(x):
    return f"{x:g}".replace(".", ",")


def potenza_contatore_stimata(load: pd.Series, standard=(1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6,
                                                         7, 8, 9, 10, 15)) -> tuple[float, float]:
    """Picco medio sul quarto d'ora [kW] e potenza impegnata minima compatibile
    (la potenza disponibile e' la impegnata + 10%)."""
    picco = float(load.max() * 4)
    for p in standard:
        if p * 1.1 >= picco:
            return picco, float(p)
    return picco, float(standard[-1])


def valuta_preventivo(load, pv1, kwp, kwh, kwh_list, batt_tpl: sim.Battery, soglia,
                      kwp_cap=None, lim_kw=0.0, prod_bassa=0.6, prod_alta=1.3):
    consumo = load.sum()
    kl = sorted(set(kwh_list) | {float(kwh)})
    g = sim.scan(load, pv1, [kwp], kl, batt_tpl, lim_kw).set_index("kwh", drop=False)
    rif = sim.knee(g.reset_index(drop=True), soglia)["kwh_ginocchio"].iloc[0]
    passo = kl[1] - kl[0] if len(kl) > 1 else 2.5
    r = g.loc[float(kwh)]
    out = {"kwp": kwp, "kwh": kwh, "r": r, "kwh_rif": rif, "r_rif": g.loc[rif], "messaggi": []}

    rapp = r["produzione"] / consumo
    if rapp < prod_bassa:
        out["fv"] = "piccolo"
        out["messaggi"].append(
            f"Il fotovoltaico produce circa il {rapp:.0%} di quanto consumi in un anno: copre poco. "
            "Se il tetto lo permette, un impianto più grande aumenterebbe l'autonomia.")
    elif rapp > prod_alta:
        out["fv"] = "grande"
        out["messaggi"].append(
            f"Il fotovoltaico produce circa il {rapp:.0%} di quanto consumi: ne usi direttamente o "
            f"con la batteria il {r['autoconsumo']:.0%}, il resto va in rete a un prezzo più basso. "
            "Ha senso se prevedi consumi in crescita (pompa di calore, auto elettrica).")
    else:
        out["fv"] = "adeguato"
        out["messaggi"].append(
            f"Il fotovoltaico produce circa il {rapp:.0%} di quanto consumi in un anno: "
            "una taglia coerente con i tuoi consumi.")
    if kwp_cap and kwp > kwp_cap:
        out["messaggi"].append(
            f"Con la superficie indicata ci stanno circa {_n(kwp_cap)} kW: verifica che l'impianto ci stia.")

    if kwh <= 0:
        out["batteria"] = "assente"
        if rif > 0:
            out["messaggi"].append(
                f"Senza batteria copri il {r['autosufficienza']:.0%} dei consumi; con circa {_n(rif)} kWh "
                f"arriveresti al {g.loc[rif]['autosufficienza']:.0%}.")
    elif kwh < rif - passo / 2:
        out["batteria"] = "piccola"
        out["messaggi"].append(
            f"La batteria è piccola per questo impianto: si riempie del tutto {int(r['giorni_piena'])} giorni "
            f"l'anno. Con circa {_n(rif)} kWh l'autonomia salirebbe dal {r['autosufficienza']:.0%} "
            f"al {g.loc[rif]['autosufficienza']:.0%}.")
    elif kwh > rif + passo / 2:
        out["batteria"] = "grande"
        out["messaggi"].append(
            f"La batteria è più grande di quanto serve: oltre circa {_n(rif)} kWh ogni kWh in più aggiunge "
            f"poca autonomia. Con {_n(rif)} kWh copriresti il {g.loc[rif]['autosufficienza']:.0%} dei consumi "
            f"invece del {r['autosufficienza']:.0%}. Potresti valutare con l'installatore una batteria più piccola.")
    else:
        out["batteria"] = "adeguata"
        out["messaggi"].append(
            f"La batteria è dimensionata bene per questo impianto: lavora circa {r['cicli']:.0f} cicli "
            f"all'anno e si riempie del tutto {int(r['giorni_piena'])} giorni l'anno.")
    return out
