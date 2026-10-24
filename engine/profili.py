"""Profili di consumo STIMATI, per chi non ha la curva quartoraria del Portale Consumi.

Due ingressi semplici; l'uscita e' un "anno tipo" 365 x 96 (kWh per quarto d'ora) sul
calendario di riferimento non bisestile del parser (ANNO_RIF), oppure la stessa cosa come
Series da 35.040 valori (ProfiloStimato.serie), identica a quella di parser.build_load_year.

    da_fasce(f1, f2, f3, ...)         kWh per fascia F1/F2/F3 (annuali, mensili o matrice 12x3)
    da_consumo_annuo(kwh, ...)        solo kWh annui + presenza in casa di giorno

LA FORMA viene dai dati aperti ARERA "Monitoraggio retail" 2025 (prelievo medio orario dei
clienti domestici residenti, per regione, classe di potenza, mese e tipo di giorno),
condensati in engine/dati/forme_arera_2025.json da scripts/prepara_forme_arera.py.
Le quote F1/F2/F3 ricostruite da quelle curve coincidono con quelle pubblicate da ARERA.

IPOTESI RESIDUE (non ricavate da dati, da tenere dichiarate):
- presenza in casa (PRES_FATTORE) e pompa di calore (PDC_RAPPORTO): ARERA non le distingue;
- rugosita: le curve ARERA sono medie di molte utenze e quindi lisce, mentre una famiglia
  reale ha picchi; senza rugosita l'autoconsumo diretto risulterebbe sovrastimato;
- le curve includono anche chi ha gia' FV (prelievo netto): leggero difetto nelle ore centrali.

LIMITI da dichiarare nell'app:
- i picchi reali non si vedono: la potenza del contatore NON va dedotta da un profilo
  stimato (ProfiloStimato.picchi_affidabili = False).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- ipotesi ---
ANNO_RIF = 2023  # non bisestile; deve coincidere con parser.REF_YEAR
DATI_ARERA = Path(__file__).resolve().parent / "dati" / "forme_arera_2025.json"

CLASSI = ("1_5_a_3", "3_a_4_5", "4_5_a_6")
CLASSE_ETICHETTA = {"1_5_a_3": "1,5–3 kW", "3_a_4_5": "3–4,5 kW", "4_5_a_6": "4,5–6 kW"}
PRESENZE = ("sempre", "a volte", "quasi mai")

# Moltiplicatore dei consumi nei giorni feriali tra le 8:30 e le 18:00, rispetto alla famiglia
# media ARERA ("a volte" = media, nessuna modifica). Ipotesi di lavoro, non da dati.
PRES_FATTORE = {"sempre": 1.35, "a volte": 1.00, "quasi mai": 0.70}

# Rapporto mensile (gen..dic) tra casa con pompa di calore come unico riscaldamento e casa
# media. Ipotesi di lavoro; conta solo la forma, il totale annuo e' sempre quello dichiarato.
PDC_RAPPORTO = np.array([1.38, 1.29, 1.05, 0.86, 0.76, 0.79, 0.83, 0.83, 0.81, 0.90, 1.10, 1.32])

RUGOSITA_PREDEFINITA = 0.5   # coefficiente di variazione dei quarti d'ora attorno alla forma liscia
SEME = 12345                 # riproducibilita: stesso input, stesso risultato


# --------------------------------------------------------------- calendario ---
def _pasqua(anno: int) -> date:
    a = anno % 19
    b, c = divmod(anno, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese, giorno = divmod(h + l - 7 * m + 114, 31)
    return date(anno, mese, giorno + 1)


def _festivi(anno: int) -> set[date]:
    fissi = [(1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15), (11, 1), (12, 8), (12, 25), (12, 26)]
    f = {date(anno, m, g) for m, g in fissi}
    f.add(_pasqua(anno) + timedelta(days=1))
    return f


@lru_cache(maxsize=4)
def _calendario(anno: int = ANNO_RIF):
    """Per ogni giorno: mese (0-11) e tipo (0 feriale, 1 sabato, 2 domenica o festivo)."""
    festivi = _festivi(anno)
    giorni = [date(anno, 1, 1) + timedelta(days=i) for i in range(365)]
    mese = np.array([g.month - 1 for g in giorni])
    tipo = np.zeros(365, dtype=int)
    for i, g in enumerate(giorni):
        if g in festivi or g.weekday() == 6:
            tipo[i] = 2
        elif g.weekday() == 5:
            tipo[i] = 1
    return mese, tipo


@lru_cache(maxsize=4)
def mappa_fasce(anno: int = ANNO_RIF) -> np.ndarray:
    """Fascia ARERA (0=F1, 1=F2, 2=F3) per ogni quarto d'ora, shape (365, 96).

    F1: lun-ven 8-19. F2: lun-ven 7-8 e 19-23, sabato 7-23. F3: notte (23-7), domeniche e festivi.
    """
    _, tipo = _calendario(anno)
    ora = np.arange(96) // 4
    out = np.full((365, 96), 2, dtype=int)
    for i, t in enumerate(tipo):
        if t == 0:
            out[i, (ora >= 8) & (ora < 19)] = 0
            out[i, ((ora >= 7) & (ora < 8)) | ((ora >= 19) & (ora < 23))] = 1
        elif t == 1:
            out[i, (ora >= 7) & (ora < 23)] = 1
    return out


# -------------------------------------------------------------- dati ARERA ---
@lru_cache(maxsize=1)
def _dati() -> dict:
    with open(DATI_ARERA, encoding="utf-8") as f:
        return json.load(f)


def regioni_disponibili() -> list[str]:
    return sorted(_dati()["regioni"])


def _norm(s: str) -> str:
    return (s.lower().replace("’", "'").replace("-", " ").replace("ü", "u").strip())


def regione_arera(nome: str | None) -> str | None:
    """Fa corrispondere il nome di una regione (come lo danno OSM o Open-Meteo) a quello ARERA."""
    if not nome:
        return None
    n = _norm(nome)
    if any(k in n for k in ("trentino", "alto adige", "sudtirol")):
        return "Trentino-Alto Adige"
    if "aosta" in n:
        return "Valle d'Aosta"
    for r in regioni_disponibili():
        rn = _norm(r)
        if rn == n or rn in n or n in rn:
            return r
    return None


@lru_cache(maxsize=64)
def _forma(regione: str | None, classe: str) -> tuple[np.ndarray, float]:
    """Prelievo medio orario (12, 3, 24) [kWh/h] e consumo annuo tipico [kWh] per la classe.

    Se la regione non e' nota si usa la media (non pesata) delle regioni."""
    reg = _dati()["regioni"]
    if regione in reg:
        v = reg[regione][classe]
        return np.array(v["ore"]), float(v["kwh_anno"])
    ore = np.mean([np.array(r[classe]["ore"]) for r in reg.values()], axis=0)
    kwh = float(np.mean([r[classe]["kwh_anno"] for r in reg.values()]))
    return ore, kwh


def consumo_tipico(regione: str | None) -> dict[str, float]:
    """Consumo annuo medio [kWh] di un'abitazione residente, per classe di potenza."""
    return {c: _forma(regione, c)[1] for c in CLASSI}


def scegli_classe(kwh_anno: float, regione: str | None = None) -> str:
    """Classe di potenza il cui consumo tipico e' piu' vicino (in scala logaritmica)."""
    tip = consumo_tipico(regione)
    return min(CLASSI, key=lambda c: abs(np.log(max(kwh_anno, 1.0) / tip[c])))


def quote_fasce_tipiche(regione: str | None, classe: str) -> np.ndarray:
    """Quote F1/F2/F3 di un'abitazione tipica (somma 1)."""
    Q = _quarti_anno(regione, classe)
    f = mappa_fasce()
    s = np.array([Q[f == k].sum() for k in range(3)])
    return s / s.sum()


# ------------------------------------------------------------------- forme ---
def _quarti(H: np.ndarray) -> np.ndarray:
    """24 valori orari [kWh/h] -> 96 quarti d'ora [kWh], energia di ogni ora conservata."""
    centri = np.arange(24) + 0.5
    xq = (np.arange(96) + 0.5) / 4.0
    q = np.interp(xq, np.r_[-0.5, centri, 24.5], np.r_[H[-1], H, H[0]]).reshape(24, 4)
    q *= (H / np.maximum(q.sum(axis=1), 1e-12))[:, None]
    return q.ravel()


@lru_cache(maxsize=64)
def _quarti_tabella(regione: str | None, classe: str) -> np.ndarray:
    """(12, 3, 96): kWh per quarto d'ora del cliente medio, per mese e tipo di giorno."""
    H, _ = _forma(regione, classe)
    return np.array([[_quarti(H[m, t]) for t in range(3)] for m in range(12)])


def _quarti_anno(regione, classe) -> np.ndarray:
    mese, tipo = _calendario()
    return _quarti_tabella(regione, classe)[mese, tipo]


def _pesi(regione, classe, presenza, pompa_calore, rugosita, seme) -> np.ndarray:
    Q = _quarti_tabella(regione, classe).copy()
    if presenza != "a volte":
        t = (np.arange(96) + 0.5) / 4.0
        fin = 1 / (1 + np.exp(-(t - 8.5) * 3)) - 1 / (1 + np.exp(-(t - 18.0) * 3))
        Q[:, 0, :] *= 1 + (PRES_FATTORE[presenza] - 1) * fin
    if pompa_calore:
        Q *= PDC_RAPPORTO[:, None, None]
    mese, tipo = _calendario()
    W = Q[mese, tipo]
    if rugosita > 0:
        sigma = np.sqrt(np.log(1 + rugosita ** 2))
        rng = np.random.default_rng(seme)
        W = W * rng.lognormal(mean=-sigma ** 2 / 2, sigma=sigma, size=W.shape)
    return W


# ---------------------------------------------------------------- risultato ---
@dataclass
class ProfiloStimato:
    anno: np.ndarray                      # (365, 96) kWh per quarto d'ora
    metodo: str                           # fasce_matrice | fasce_mensili | fasce_annuali | consumo_annuo
    regione: str | None = None            # regione ARERA da cui viene la forma (None = media italiana)
    classe: str = "3_a_4_5"
    avvisi: list[str] = field(default_factory=list)
    picchi_affidabili: bool = False       # sempre False: non stimare il contatore da qui
    residuo_max_pct: float = 0.0          # scostamento massimo dai totali inseriti dopo l'adattamento

    @property
    def totale_kwh(self) -> float:
        return float(self.anno.sum())

    @property
    def serie(self) -> pd.Series:
        """Stessa forma di parser.build_load_year: Series di 35.040 valori [kWh/15 min]."""
        idx = pd.date_range(f"{ANNO_RIF}-01-01", periods=365 * 96, freq="15min")
        return pd.Series(self.anno.ravel(), index=idx, name="load_kwh")

    @property
    def descrizione(self) -> str:
        dove = f"regione {self.regione}" if self.regione else "media italiana"
        return {
            "fasce_matrice": "fasce F1/F2/F3 mese per mese",
            "fasce_mensili": "fasce F1/F2/F3 e consumi mensili",
            "fasce_annuali": "fasce F1/F2/F3 annuali",
            "consumo_annuo": "solo consumo annuo",
        }[self.metodo] + f"; forma tipica dei consumi domestici da dati ARERA 2025 ({dove})"

    @property
    def incertezza(self) -> str:
        return {
            "fasce_matrice": "bassa-media: mesi e fasce rispettati, solo la forma dentro la fascia e' ipotizzata",
            "fasce_mensili": "media: totali per fascia e per mese rispettati, forma tipica regionale",
            "fasce_annuali": "media-alta: stagionalita' e forma tipiche della regione",
            "consumo_annuo": "alta: solo il totale e' noto; forma e stagionalita' tipiche della regione",
        }[self.metodo]


# ------------------------------------------------------------ adattamento ---
def _adatta(W, fasce, tot_fasce=None, tot_mesi=None, matrice=None, iterazioni=200):
    """Scala i pesi perche' i totali richiesti siano rispettati (fitting proporzionale iterativo)."""
    mese, _ = _calendario()
    W = W.copy()
    mask_f = [fasce == f for f in range(3)]
    mask_m = [(mese == m)[:, None] & np.ones((1, 96), bool) for m in range(12)]
    if matrice is not None:
        for m in range(12):
            for f in range(3):
                celle = mask_m[m] & mask_f[f]
                s = W[celle].sum()
                W[celle] *= (matrice[m][f] / s) if s > 0 else 0.0
        return W
    for _ in range(iterazioni):
        if tot_mesi is not None:
            for m in range(12):
                s = W[mask_m[m]].sum()
                W[mask_m[m]] *= (tot_mesi[m] / s) if s > 0 else 0.0
        for f in range(3):
            s = W[mask_f[f]].sum()
            W[mask_f[f]] *= (tot_fasce[f] / s) if s > 0 else 0.0
    return W


def _residuo(W, fasce, tot_fasce, tot_mesi=None):
    mese, _ = _calendario()
    r = [abs(W[fasce == f].sum() - tot_fasce[f]) / max(tot_fasce[f], 1e-9) for f in range(3) if tot_fasce[f] > 0]
    if tot_mesi is not None:
        for m in range(12):
            if tot_mesi[m] > 0:
                r.append(abs(W[(mese == m)[:, None] & np.ones((1, 96), bool)].sum() - tot_mesi[m]) / tot_mesi[m])
    return 100 * max(r) if r else 0.0


def _controlli_totale(kwh: float) -> list[str]:
    if kwh < 500:
        return [f"Consumo annuo molto basso ({kwh:.0f} kWh): controlla il valore."]
    if kwh > 15000:
        return [f"Consumo annuo molto alto ({kwh:.0f} kWh) per un'abitazione: controlla il valore."]
    return []


def _regione(regione):
    r = regione_arera(regione)
    return r if r in _dati()["regioni"] else None


# ------------------------------------------------------------- ingressi ---
def da_fasce(f1: float, f2: float, f3: float, *,
             mensili: list[float] | None = None,
             matrice: list[list[float]] | None = None,
             regione: str | None = None,
             presenza: str = "a volte",
             pompa_calore: bool = False,
             rugosita: float = RUGOSITA_PREDEFINITA,
             seme: int = SEME) -> ProfiloStimato:
    """Anno tipo da kWh annui per fascia F1/F2/F3.

    mensili: 12 totali mensili (kWh), facoltativi.
    matrice: 12 x 3 kWh per mese e fascia (dalle bollette); ha la precedenza su f1/f2/f3 e mensili.
    presenza: conta poco, perche' il livello lo decidono i kWh per fascia inseriti.
    """
    if presenza not in PRESENZE:
        raise ValueError(f"presenza deve essere una tra {PRESENZE}")
    avvisi: list[str] = []
    reg = _regione(regione)
    fasce = mappa_fasce()

    if matrice is not None:
        m = np.asarray(matrice, dtype=float)
        if m.shape != (12, 3) or (m < 0).any():
            raise ValueError("matrice deve essere 12 x 3 con valori >= 0")
        tot_fasce, tot_mesi, metodo = m.sum(axis=0), None, "fasce_matrice"
    else:
        m = None
        tot_fasce = np.array([f1, f2, f3], dtype=float)
        if (tot_fasce < 0).any():
            raise ValueError("i kWh per fascia non possono essere negativi")
        tot_mesi, metodo = None, "fasce_annuali"
        if mensili is not None:
            tot_mesi = np.asarray(mensili, dtype=float)
            if tot_mesi.shape != (12,) or (tot_mesi < 0).any():
                raise ValueError("mensili deve avere 12 valori >= 0")
            scarto = abs(tot_mesi.sum() - tot_fasce.sum()) / max(tot_fasce.sum(), 1e-9)
            if scarto > 0.03:
                avvisi.append(
                    f"La somma dei mesi ({tot_mesi.sum():.0f} kWh) differisce dal totale delle fasce "
                    f"({tot_fasce.sum():.0f} kWh) del {100 * scarto:.0f}%: i mesi sono stati riportati al totale delle fasce.")
            tot_mesi = tot_mesi * tot_fasce.sum() / max(tot_mesi.sum(), 1e-9)
            metodo = "fasce_mensili"

    tot = float(tot_fasce.sum())
    if tot <= 0:
        raise ValueError("il consumo totale deve essere maggiore di zero")
    classe = scegli_classe(tot, reg)
    W = _pesi(reg, classe, presenza, pompa_calore, rugosita, seme)
    W = _adatta(W, fasce, tot_fasce=tot_fasce, tot_mesi=tot_mesi, matrice=m)

    tip = quote_fasce_tipiche(reg, classe)
    quote = tot_fasce / tot
    if abs(quote[0] - tip[0]) > 0.15:
        avvisi.append(f"La quota in F1 ({100 * quote[0]:.0f}%) si discosta molto da quella tipica "
                      f"({100 * tip[0]:.0f}%): controlla i valori inseriti.")
    avvisi += _controlli_totale(tot)
    res = _residuo(W, fasce, tot_fasce, tot_mesi) if m is None else 0.0
    return ProfiloStimato(anno=W, metodo=metodo, regione=reg, classe=classe, avvisi=avvisi, residuo_max_pct=res)


def da_consumo_annuo(kwh_anno: float, *,
                     regione: str | None = None,
                     presenza: str = "a volte",
                     pompa_calore: bool = False,
                     rugosita: float = RUGOSITA_PREDEFINITA,
                     seme: int = SEME) -> ProfiloStimato:
    """Anno tipo dal solo consumo annuo e dalla presenza in casa di giorno."""
    if presenza not in PRESENZE:
        raise ValueError(f"presenza deve essere una tra {PRESENZE}")
    if kwh_anno <= 0:
        raise ValueError("il consumo annuo deve essere maggiore di zero")
    reg = _regione(regione)
    classe = scegli_classe(kwh_anno, reg)
    W = _pesi(reg, classe, presenza, pompa_calore, rugosita, seme)
    W *= kwh_anno / W.sum()
    avvisi = _controlli_totale(kwh_anno)
    avvisi.append("Profilo stimato dal solo consumo annuo: autoconsumo e autonomia sono indicativi. "
                  "Con le fasce della bolletta o con la curva del Portale Consumi il risultato è più affidabile.")
    return ProfiloStimato(anno=W, metodo="consumo_annuo", regione=reg, classe=classe, avvisi=avvisi)
