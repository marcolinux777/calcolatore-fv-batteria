"""Stile climaction per Streamlit e Plotly.

Trasposizione di climaction_palette.py (v1.1, agosto 2026) per l'app web.
Regola di fondo: un solo significato per colore.
  Rosso  = soglia superata, evidenza (qui: la proposta, le soglie dell'obiettivo).
  Blu    = dato neutro / "freddo" (qui: i consumi).
  Verde  = colore del sito; nei grafici solo per la sintesi (qui: energia solare usata).
  Ocra   = sole/estate (qui: produzione fotovoltaica).
  Grigio = contesto, mai protagonista (qui: energia dalla rete, alternative).
"""
import plotly.graph_objects as go
import plotly.io as pio
import base64
from pathlib import Path

import streamlit as st

# ---- colori nominali del sito
CARTA = "#FAF8F5"        # fondo pagina e figure
TESTO = "#1A1A1A"        # titoli, assi
TESTO_SOFT = "#6E6E6E"   # didascalie, tick
GRIGLIA = "#E2DDD6"      # griglie e bordi
VERDE = "#2F5D46"        # primario, marchio, sintesi
VERDE_CH = "#6B8F71"
ROSSO = "#C4442A"        # evidenza, soglie
BLU = "#14415B"          # dato neutro
# ruoli
MODELLI = "#B9B4AC"      # contesto
NEUTRO = "#9A948B"       # termine di confronto
OCRA = "#C98A28"         # estate / sole
RUGGINE = "#9C5330"      # autunno

STAGIONI = {"Inverno": BLU, "Primavera": VERDE_CH, "Estate": OCRA, "Autunno": RUGGINE}
QUALITATIVA = [BLU, VERDE_CH, OCRA, RUGGINE, VERDE]
GIUDIZIO = ["#2F5D46", "#7FA687", "#D9C46B", "#D08A46", "#C4442A"]  # buona -> critica

FONT_CORPO = "'Source Sans 3', 'Source Sans Pro', sans-serif"
FONT_TITOLI = "'Source Serif 4', Georgia, serif"


def _hex(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def rampa(n, scuro=VERDE, chiaro="#E4ECE5"):
    """n colori ordinati dal chiaro allo scuro (per categorie ordinali, es. taglie di batteria)."""
    a, b = _hex(chiaro), _hex(scuro)
    if n == 1:
        return [scuro]
    return ["#%02X%02X%02X" % tuple(round(a[k] + (b[k] - a[k]) * i / (n - 1)) for k in range(3))
            for i in range(n)]


def trasparente(h, alpha):
    r, g, b = _hex(h)
    return f"rgba({r},{g},{b},{alpha})"


# scale continue (heatmap): dal fondo carta al colore pieno
SCALA_FREDDO = [[0, CARTA], [0.5, "#8FA6B4"], [1, BLU]]

# ---- template Plotly
pio.templates["climaction"] = go.layout.Template(layout=dict(
    font=dict(family=FONT_CORPO, size=15, color=TESTO),
    title=dict(font=dict(size=18, color=TESTO, family=FONT_CORPO, weight=600), x=0, xanchor="left"),
    paper_bgcolor=CARTA, plot_bgcolor=CARTA,
    colorway=QUALITATIVA,
    xaxis=dict(gridcolor=GRIGLIA, linecolor=GRIGLIA, zeroline=False, ticks="outside",
               tickcolor=GRIGLIA, tickfont=dict(color=TESTO_SOFT, size=14), title=dict(font=dict(color=TESTO))),
    yaxis=dict(gridcolor=GRIGLIA, linecolor=GRIGLIA, zeroline=False, ticks="outside",
               tickcolor=GRIGLIA, tickfont=dict(color=TESTO_SOFT, size=14), title=dict(font=dict(color=TESTO))),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=TESTO_SOFT, size=14), orientation="h", y=-0.26),
    hoverlabel=dict(bgcolor="white", bordercolor=GRIGLIA, font=dict(color=TESTO, family=FONT_CORPO)),
    margin=dict(l=10, r=10, t=52, b=10),
))
pio.templates.default = "climaction"

# ---- CSS: font del sito, titoli serif, bordi e riquadri in tono
CSS = f"""
<style>
html {{ font-size: 18px; }}            /* base più grande: tutto ciò che è in rem scala */
.stMarkdown p, .stMarkdown li, label p, [data-testid="stWidgetLabel"] p {{ font-size: 1.02rem; }}
[data-testid="stCaptionContainer"], .stCaption {{ font-size: 0.95rem !important; }}
[data-testid="stMetricLabel"] p {{ font-size: 0.98rem !important; }}
[data-testid="stMetricValue"] {{ font-size: 2.1rem !important; }}
[data-testid="stExpander"] summary p {{ font-size: 1.05rem; }}
[role="radiogroup"] label p, [data-testid="stCheckbox"] label p {{ font-size: 1.02rem !important; }}
[data-baseweb="select"] div, [data-baseweb="input"] input, .stNumberInput input {{ font-size: 1rem !important; }}
.stButton button p, .stLinkButton a p, [data-testid="stLinkButton"] p {{ font-size: 0.98rem !important; }}
h1 {{ font-size: 2.4rem !important; line-height: 1.15 !important; }}
@import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&family=Source+Serif+4:opsz,wght@8..60,600;8..60,700&family=JetBrains+Mono&display=swap');
html, body, [class*="css"], .stMarkdown, .stCaption, label, input, textarea, button {{
    font-family: {FONT_CORPO};
}}
h1, h2, h3, h4 {{ font-family: {FONT_TITOLI} !important; color: {TESTO}; letter-spacing: -0.01em; }}
h1 {{ font-weight: 700 !important; }}
code, pre {{ font-family: 'JetBrains Mono', monospace; }}
[data-testid="stCaptionContainer"], .stCaption {{ color: {TESTO_SOFT}; }}
[data-testid="stMetricValue"] {{ color: {VERDE}; }}
[data-testid="stMetricLabel"] p {{ color: {TESTO_SOFT}; }}
[data-testid="stExpander"] details, [data-testid="stVerticalBlockBorderWrapper"] {{ border-color: {GRIGLIA} !important; }}
[data-testid="stExpander"] summary:hover {{ color: {VERDE}; }}
hr {{ border-color: {GRIGLIA} !important; }}
a, a:visited {{ color: {VERDE}; }}
.giudizio {{ display:inline-block; padding:0.15rem 0.6rem; border-radius:999px; color:white;
            font-weight:600; font-size:1.05rem; }}
.giudizio-label {{ color:{TESTO_SOFT}; font-size:0.98rem; margin-bottom:0.2rem; }}
/* testo di Streamlit "Press Enter to apply" tradotto in italiano */
[data-testid="InputInstructions"] {{ visibility: hidden; position: relative; }}
[data-testid="InputInstructions"]::after {{
    content: "Premi Invio per applicare"; visibility: visible;
    position: absolute; right: 0; top: 0; white-space: nowrap;
}}
</style>
"""


def applica():
    """Da chiamare subito dopo st.set_page_config."""
    st.markdown(CSS, unsafe_allow_html=True)


def badge(etichetta, testo, livello):
    """Etichetta di giudizio colorata. livello: 0 = buona ... 4 = critica, None = neutro."""
    col = NEUTRO if livello is None else GIUDIZIO[livello]
    st.markdown(f"<div class='giudizio-label'>{etichetta}</div>"
                f"<span class='giudizio' style='background:{col}'>{testo}</span>",
                unsafe_allow_html=True)


def carica_logo(percorso) -> bytes | None:
    """Legge il logo (PNG) dalla cartella assets; None se il file non c'è."""
    p = Path(percorso)
    return p.read_bytes() if p.exists() else None


def logo_html(href, png: bytes, px=64):
    """Logo climaction cliccabile (apre il sito in una nuova scheda)."""
    b64 = base64.b64encode(png).decode()
    return (f"<a href='{href}' target='_blank' title='climaction.it'>"
            f"<img src='data:image/png;base64,{b64}' width='{px}' alt='climaction' "
            f"style='display:block'></a>")
