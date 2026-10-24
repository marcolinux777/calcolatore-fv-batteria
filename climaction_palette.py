"""
climaction — palette e stile per matplotlib
Versione 1.1, agosto 2026.

Uso:
    import climaction_palette as cp
    cp.apply()                      # stile globale + avviso se i font mancano
    cp.apply(strict=True)           # errore bloccante se i font mancano
    fig, ax = plt.subplots()
    ax.plot(x, y, color=cp.ENSEMBLE)
    ax.imshow(z, cmap=cp.cmap('divergente'), vmin=-5, vmax=5)
    fig.savefig('figura.png', **cp.SAVE)

Regola di fondo: un solo significato per colore.
Rosso = caldo / superamento. Blu = freddo, umido, meno rischio.
Verde = colore del sito; nei grafici solo per la sintesi (ensemble, mediana)
o per la vegetazione. Grigio = contesto, mai protagonista.
"""

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

# --------------------------------------------------------------------------
# 1. Colori nominali del sito
# --------------------------------------------------------------------------
CARTA      = "#FAF8F5"   # fondo figura e pagina
TESTO      = "#1A1A1A"   # assi, titoli
TESTO_SOFT = "#6E6E6E"   # didascalie, tick secondari
GRIGLIA    = "#E2DDD6"   # griglia e bordi
VERDE      = "#2F5D46"   # primario del sito, marchio
VERDE_CH   = "#6B8F71"   # verde chiaro del marchio
ROSSO      = "#C4442A"   # accento: soglia superata, evidenza critica
BLU        = "#14415B"   # dato "freddo", serie neutra

# ruoli ricorrenti nei grafici
ENSEMBLE   = VERDE       # linea di sintesi / media dei modelli
MODELLI    = "#B9B4AC"   # spaghetti dei singoli modelli, contesto
EVIDENZA   = ROSSO       # ciò che si vuole far vedere
SOGLIA     = ROSSO       # linee di soglia (tratteggiate)
NEUTRO     = "#9A948B"   # dato "già noto", sfondo del confronto

# --------------------------------------------------------------------------
# 2. Conversione sRGB <-> CIE Lab (per costruire rampe a luminanza monotona)
# --------------------------------------------------------------------------
_M = np.array([[0.4124, 0.3576, 0.1805],
               [0.2126, 0.7152, 0.0722],
               [0.0193, 0.1192, 0.9505]])
_WP = np.array([0.95047, 1.0, 1.08883])


def _hex2rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)]) / 255.0


def _rgb2hex(rgb):
    rgb = np.clip(rgb, 0, 1)
    return "#%02X%02X%02X" % tuple((rgb * 255).round().astype(int))


def _srgb2lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _lin2srgb(c):
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.clip(c, 0, None) ** (1 / 2.4) - 0.055)


def _f(t):
    return np.where(t > 0.008856, np.cbrt(t), 7.787 * t + 16 / 116)


def _finv(t):
    return np.where(t ** 3 > 0.008856, t ** 3, (t - 16 / 116) / 7.787)


def rgb2lab(rgb):
    xyz = _M @ _srgb2lin(np.asarray(rgb))
    f = _f(xyz / _WP)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def lab2rgb(lab):
    L, a, b = lab
    fy = (L + 16) / 116
    xyz = _WP * _finv(np.array([fy + a / 500, fy, fy - b / 200]))
    return _lin2srgb(np.linalg.inv(_M) @ xyz)


def _max_chroma(L, hue, hi=140.0):
    lo = 0.0
    for _ in range(24):
        mid = (lo + hi) / 2
        rgb = lab2rgb([L, hue[0] * mid, hue[1] * mid])
        if np.all(rgb > -1e-4) and np.all(rgb < 1 + 1e-4):
            lo = mid
        else:
            hi = mid
    return lo


def _ramp(anchor, n=256, L_hi=96.0, L_lo=27.0):
    """Rampa monocromatica: luminanza monotona, croma massima compatibile col gamut."""
    lab = rgb2lab(_hex2rgb(anchor))
    C = np.hypot(lab[1], lab[2])
    hue = np.array([lab[1], lab[2]]) / C if C > 0 else np.array([0.0, 0.0])
    t = np.linspace(0, 1, n)
    Ls = L_hi + (L_lo - L_hi) * t
    # profilo di croma: quasi nulla sul chiaro, piena sul medio-scuro
    prof = 0.06 + 0.94 * t ** 0.55
    cols = []
    for i in range(n):
        Cmax = _max_chroma(Ls[i], hue)
        Ci = min(C * 1.35 * prof[i], Cmax * 0.94)
        cols.append(np.clip(lab2rgb([Ls[i], hue[0] * Ci, hue[1] * Ci]), 0, 1))
    return np.array(cols)


# --------------------------------------------------------------------------
# 3. Colormap
# --------------------------------------------------------------------------
def _make():
    caldo = _ramp(ROSSO)                       # sequenziale caldo
    freddo = _ramp(BLU)                        # sequenziale freddo
    vegeta = _ramp(VERDE)                      # sequenziale vegetazione/idrico

    # divergente: blu -> carta -> rosso, con luminanza a tetto al centro
    n = 128
    left = _ramp(BLU, n=n, L_hi=93, L_lo=30)[::-1]
    right = _ramp(ROSSO, n=n, L_hi=93, L_lo=30)
    diverg = np.vstack([left, right])

    cmaps = {
        "caldo":       LinearSegmentedColormap.from_list("climaction_caldo", caldo),
        "freddo":      LinearSegmentedColormap.from_list("climaction_freddo", freddo),
        "vegetazione": LinearSegmentedColormap.from_list("climaction_vegetazione", vegeta),
        "divergente":  LinearSegmentedColormap.from_list("climaction_divergente", diverg),
    }
    # scala di giudizio ordinale (idoneità, semaforo) — 5 gradini, non continua
    return cmaps


_CMAPS = _make()


def cmap(nome):
    """caldo | freddo | vegetazione | divergente (aggiungi '_r' per invertire)."""
    rev = nome.endswith("_r")
    base = nome[:-2] if rev else nome
    c = _CMAPS[base]
    return c.reversed() if rev else c


# --------------------------------------------------------------------------
# 4. Palette discrete
# --------------------------------------------------------------------------
# categorie qualitative, max 5 — pensata per le stagioni
STAGIONI = {
    "Inverno":   BLU,
    "Primavera": VERDE_CH,
    "Estate":    "#C98A28",
    "Autunno":   "#9C5330",
}
QUALITATIVA = [BLU, VERDE_CH, "#C98A28", "#9C5330", VERDE]

# giudizio ordinale: buona -> critica. Usare SOLO dove il giudizio è dichiarato.
GIUDIZIO = ["#2F5D46", "#7FA687", "#D9C46B", "#D08A46", "#C4442A"]
GIUDIZIO_ETICHETTE = ["buona", "discreta", "sufficiente", "scarsa", "critica"]

# confronto a due: contesto + evidenza
CONFRONTO = [NEUTRO, ROSSO]


# --------------------------------------------------------------------------
# 5. Stile globale
# --------------------------------------------------------------------------
RC = {
    "figure.facecolor":   CARTA,
    "savefig.facecolor":  CARTA,
    "axes.facecolor":     CARTA,
    "axes.edgecolor":     GRIGLIA,
    "axes.linewidth":     0.8,
    "axes.grid":          True,
    "axes.axisbelow":     True,
    "axes.labelcolor":    TESTO,
    "axes.titlecolor":    TESTO,
    "axes.titlesize":     13,
    "axes.titleweight":   "semibold",
    "axes.titlepad":      12,
    "axes.labelsize":     11,
    "axes.spines.top":    False,
    "axes.spines.right":  False,
    "grid.color":         GRIGLIA,
    "grid.linewidth":     0.7,
    "text.color":         TESTO,
    "xtick.color":        TESTO_SOFT,
    "ytick.color":        TESTO_SOFT,
    "xtick.labelsize":    10,
    "ytick.labelsize":    10,
    "xtick.direction":    "out",
    "ytick.direction":    "out",
    "legend.frameon":     False,
    "legend.fontsize":    10,
    "font.size":          11,
    "font.family":        "sans-serif",
    "font.sans-serif":    ["Source Sans 3", "Source Sans Pro", "DejaVu Sans"],
    "axes.prop_cycle":    mpl.cycler(color=QUALITATIVA),
    "figure.dpi":         110,
    "savefig.dpi":        200,
    "savefig.bbox":       "tight",
}

SAVE = dict(dpi=200, bbox_inches="tight", facecolor=CARTA)


# --------------------------------------------------------------------------
# 6. Controllo font
# --------------------------------------------------------------------------
# matplotlib, se la famiglia richiesta non è installata, ripiega in silenzio
# su DejaVu Sans: le figure escono tipograficamente diverse dal sito e non
# c'è nessun errore che lo segnali. Qui il ripiego diventa esplicito.

FONT_ATTESO = "Source Sans 3"
FONT_SITO = ["Source Serif 4", "Source Sans 3", "JetBrains Mono"]


def font_installati():
    """Stato dei tre font del sito: {nome: True/False}."""
    import matplotlib.font_manager as fm
    presenti = {f.name for f in fm.fontManager.ttflist}
    return {nome: nome in presenti for nome in FONT_SITO}


def verifica_font(strict=False):
    """Avvisa se il font del corpo non c'è. strict=True solleva un errore."""
    import warnings
    import matplotlib.font_manager as fm

    presenti = {f.name for f in fm.fontManager.ttflist}
    if FONT_ATTESO in presenti:
        return True

    ripiego = next((f for f in RC["font.sans-serif"] if f in presenti), "DejaVu Sans")
    msg = (
        f"climaction: font '{FONT_ATTESO}' non installato. "
        f"matplotlib userà '{ripiego}': le figure non saranno tipograficamente "
        f"coerenti con il sito. Installa i font e svuota la cache "
        f"(vedi climaction_palette.svuota_cache_font)."
    )
    if strict:
        raise RuntimeError(msg)
    warnings.warn(msg, RuntimeWarning, stacklevel=2)
    return False


def svuota_cache_font():
    """Ricostruisce l'elenco font di matplotlib dopo un'installazione."""
    import matplotlib.font_manager as fm
    fm._load_fontmanager(try_read_cache=False)
    return font_installati()


def apply(strict=False):
    mpl.rcParams.update(RC)
    verifica_font(strict=strict)


def didascalia(fig, testo, y=-0.02):
    """Riga di fonte/periodo/scenario sotto la figura, in grigio."""
    fig.text(0.0, y, testo, ha="left", va="top", fontsize=9, color=TESTO_SOFT)


def soglia(ax, valore, etichetta=None, **kw):
    """Linea di soglia: sempre rossa, sempre tratteggiata, sempre etichettata."""
    ax.axhline(valore, color=SOGLIA, lw=1.0, ls=(0, (4, 3)), zorder=1, **kw)
    if etichetta:
        ax.annotate(etichetta, xy=(1.0, valore), xycoords=("axes fraction", "data"),
                    ha="right", va="bottom", fontsize=9, color=SOGLIA)
