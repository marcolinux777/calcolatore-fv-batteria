"""Lettura dei parametri standard da parametri.toml."""
from __future__ import annotations

import tomllib
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "parametri.toml"

RICHIESTI = {
    "costi": ["fv_eur_kwp", "batteria_eur_kwh", "batteria_fisso_eur", "manutenzione_eur_kwp_anno"],
    "energia": ["prezzo_prelievo", "valore_immissione"],
    "finanza": ["orizzonte_anni", "tasso_sconto", "inflazione_energia", "degrado_fv",
                "vita_batteria_anni", "costo_sostituzione"],
    "incentivi": [],
    "batteria": ["dod", "rendimento", "c_rate", "potenza_min_kw"],
    "fv": ["perdite", "inclinazione_falda", "inclinazione_piano", "m2_per_kwp", "kwp_max_base",
           "pvgis_anno_inizio", "pvgis_anno_fine"],
    "analisi": ["soglia_ginocchio", "passo_batteria_kwh", "batteria_max_kwh"],
    "comuni": [],
    "giudizio": ["produzione_bassa", "produzione_alta"],
    "app": ["url_istruzioni", "logo", "firma"],
}


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    mancanti = [f"[{s}] {k}" for s, keys in RICHIESTI.items()
                for k in ([s] if not keys else keys)
                if s not in cfg or (keys and k not in cfg[s])]
    if mancanti:
        raise ValueError(f"parametri.toml incompleto, mancano: {', '.join(mancanti)}")
    return cfg


def mtime(path: Path = CONFIG_PATH) -> float:
    return path.stat().st_mtime
