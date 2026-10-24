"""Esportazione in PDF dei dati di calcolo e dei risultati.

Il PDF viene generato in memoria e consegnato al browser: non viene salvato.
Grafici con matplotlib e lo stile di climaction_palette.py; font DejaVu Sans
(incluso in matplotlib) perché copre €, ², ° e lettere accentate. Se nella
cartella assets/fonts ci sono i file SourceSans3-Regular.ttf e
SourceSans3-Bold.ttf, vengono usati quelli (font del sito).
"""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib as mpl  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from fpdf import FPDF  # noqa: E402

import climaction_palette as cp  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MESI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
OCRA = "#C98A28"


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _font_files():
    src = ROOT / "assets" / "fonts"
    if (src / "SourceSans3-Regular.ttf").exists() and (src / "SourceSans3-Bold.ttf").exists():
        return src / "SourceSans3-Regular.ttf", src / "SourceSans3-Bold.ttf"
    ttf = Path(mpl.get_data_path()) / "fonts" / "ttf"
    return ttf / "DejaVuSans.ttf", ttf / "DejaVuSans-Bold.ttf"


# ---------------------------------------------------------------- grafici
def _fig_png(fig):
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    b.seek(0)
    return b


def grafico_mensile(mm: dict):
    with mpl.rc_context({**cp.RC, "figure.facecolor": "white", "axes.facecolor": "white"}):
        fig, ax = plt.subplots(figsize=(8.0, 2.55))
        x = np.arange(12)
        b1 = np.array(mm["fv_diretto"]); b2 = np.array(mm["scarica"]); b3 = np.array(mm["prelievo"])
        ax.bar(x, b1, color=cp.VERDE, label="Dal sole, subito", width=0.7)
        ax.bar(x, b2, bottom=b1, color=cp.VERDE_CH, label="Dalla batteria", width=0.7)
        ax.bar(x, b3, bottom=b1 + b2, color=cp.MODELLI, label="Dalla rete", width=0.7)
        ax.plot(x, mm["fv"], color=OCRA, ls=":", marker="o", ms=3.5, lw=1.6, label="Produzione FV")
        ax.set_xticks(x, MESI)
        ax.set_ylabel("kWh/mese")
        ax.set_title("Come vengono coperti i consumi, mese per mese", loc="left")
        ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.12))
        return _fig_png(fig)


def grafico_cassa(curve: list, orizzonte: int):
    cols = [cp.VERDE, cp.NEUTRO, cp.BLU]
    with mpl.rc_context({**cp.RC, "figure.facecolor": "white", "axes.facecolor": "white"}):
        fig, ax = plt.subplots(figsize=(8.0, 2.45))
        x = np.arange(orizzonte + 1)
        for i, (nome, y) in enumerate(curve):
            ax.plot(x, np.array(y) / 1000, color=cols[i % 3], lw=2.4 if i == 0 else 1.5, label=nome)
        ax.axhline(0, color=cp.NEUTRO, lw=0.8)
        ax.set_xlabel("anni")
        ax.xaxis.set_major_locator(mpl.ticker.MaxNLocator(integer=True))
        ax.set_ylabel("migliaia di €")
        ax.set_title("Soldi spesi e recuperati nel tempo (euro di oggi)", loc="left")
        ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.22))
        return _fig_png(fig)


# ---------------------------------------------------------------- PDF
class _PDF(FPDF):
    def __init__(self, logo_png: bytes | None, firma: str, sito: str):
        super().__init__(format="A4")
        self.logo_png, self.firma, self.sito = logo_png, firma, sito
        reg, bold = _font_files()
        self.add_font("corpo", "", str(reg))
        self.add_font("corpo", "B", str(bold))
        self.set_auto_page_break(True, margin=24)
        self.set_margins(16, 16, 16)

    def footer(self):
        self.set_y(-18)
        self.set_draw_color(*_rgb(cp.GRIGLIA))
        self.line(16, self.get_y() - 2, 194, self.get_y() - 2)
        if self.logo_png:
            self.image(io.BytesIO(self.logo_png), x=16, y=self.get_y(), h=9)
        self.set_xy(28, self.get_y() + 1)
        self.set_font("corpo", "B", 9)
        self.set_text_color(*_rgb(cp.TESTO))
        self.cell(0, 4, f"climaction · {self.firma}", new_x="LMARGIN", new_y="NEXT")
        self.set_x(28)
        self.set_font("corpo", "", 8)
        self.set_text_color(*_rgb(cp.TESTO_SOFT))
        self.cell(120, 4, self.sito)
        self.cell(0, 4, f"pagina {self.page_no()}/{{nb}}", align="R")

    # -- elementi
    def titolo(self, testo, size=16):
        self.set_font("corpo", "B", size)
        self.set_text_color(*_rgb(cp.VERDE))
        self.multi_cell(0, size * 0.5, testo, align="L", new_x="LMARGIN", new_y="NEXT")
        self.ln(1.5)

    def sezione(self, testo):
        if self.get_y() > 250:
            self.add_page()
        self.ln(2)
        self.set_font("corpo", "B", 11.5)
        self.set_text_color(*_rgb(cp.VERDE))
        self.cell(0, 6, testo, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*_rgb(cp.GRIGLIA))
        self.line(16, self.get_y(), 194, self.get_y())
        self.ln(2)

    def testo(self, t, size=9.5, colore=None):
        self.set_font("corpo", "", size)
        self.set_text_color(*_rgb(colore or cp.TESTO))
        self.multi_cell(0, size * 0.48, t, align="L", new_x="LMARGIN", new_y="NEXT")

    def coppie(self, righe, col1=62):
        """Tabella a due colonne etichetta/valore."""
        for k, v in righe:
            self.set_font("corpo", "", 9.5)
            self.set_text_color(*_rgb(cp.TESTO_SOFT))
            y = self.get_y()
            self.multi_cell(col1, 5, k, align="L", new_x="RIGHT", new_y="TOP")
            self.set_text_color(*_rgb(cp.TESTO))
            self.multi_cell(0, 5, str(v), align="L", new_x="LMARGIN", new_y="NEXT")
            self.set_y(max(self.get_y(), y + 5))

    def riquadri(self, metriche):
        """Riquadri con i numeri principali (come nell'app)."""
        n = len(metriche)
        w = (178 - (n - 1) * 3) / n
        y0, x0 = self.get_y(), 16
        self.set_draw_color(*_rgb(cp.GRIGLIA))
        self.set_fill_color(*_rgb(cp.CARTA))
        for i, (k, v) in enumerate(metriche):
            x = x0 + i * (w + 3)
            self.rect(x, y0, w, 17, style="DF")
            self.set_xy(x + 2, y0 + 2)
            self.set_font("corpo", "", 7)
            self.set_text_color(*_rgb(cp.TESTO_SOFT))
            self.multi_cell(w - 4, 3.2, k, align="L")
            self.set_xy(x + 2, y0 + 9.5)
            self.set_font("corpo", "B", 12.5)
            self.set_text_color(*_rgb(cp.VERDE))
            self.cell(w - 4, 6, v)
        self.set_y(y0 + 20)

    def tabella(self, intestazioni, righe, larghezze=None):
        n = len(intestazioni)
        larghezze = larghezze or [178 / n] * n
        self.set_draw_color(*_rgb(cp.GRIGLIA))
        self.set_fill_color(*_rgb(cp.CARTA))
        self.set_font("corpo", "B", 8)
        self.set_text_color(*_rgb(cp.TESTO))
        for h, w in zip(intestazioni, larghezze):
            self.cell(w, 6.5, h, border="B", fill=True)
        self.ln()
        self.set_font("corpo", "", 9)
        for r in righe:
            for c, w in zip(r, larghezze):
                self.cell(w, 6, str(c), border="B")
            self.ln()
        self.ln(1)

    def elenco(self, voci, size=9):
        self.set_font("corpo", "", size)
        self.set_text_color(*_rgb(cp.TESTO))
        for v in voci:
            self.set_x(18)
            self.multi_cell(0, size * 0.5, "• " + v, align="L", new_x="LMARGIN", new_y="NEXT")
            self.ln(0.6)


def genera_pdf(d: dict, logo_png: bytes | None) -> bytes:
    pdf = _PDF(logo_png, d["firma"], d["sito"])
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.titolo("Verifica del dimensionamento fotovoltaico e batteria")
    pdf.testo(f"Generato il {date.today():%d/%m/%Y} · costi e prezzi standard aggiornati a {d['aggiornamento']}",
              size=8.5, colore=cp.TESTO_SOFT)
    pdf.ln(1)

    pdf.sezione("Dati di partenza")
    pdf.coppie(d["dati"])

    pdf.sezione(d["titolo_risultato"])
    pdf.set_font("corpo", "B", 12)
    pdf.set_text_color(*_rgb(cp.TESTO))
    pdf.cell(0, 7, d["configurazione"], new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    pdf.riquadri(d["metriche"])
    pdf.coppie(d["dettagli"])
    for a in d.get("avvisi", []):
        pdf.ln(1)
        pdf.testo(a, size=8.5, colore=cp.TESTO_SOFT)

    if d.get("confronto"):
        pdf.sezione("A confronto, con lo stesso impianto fotovoltaico")
        pdf.tabella(*d["confronto"], larghezze=[36, 26, 32, 28, 22, 34])

    if d.get("preventivo"):
        pv = d["preventivo"]
        pdf.sezione("Il preventivo da verificare")
        pdf.coppie(pv["giudizi"])
        pdf.elenco(pv["messaggi"])
        pdf.testo("Il giudizio riguarda solo il dimensionamento, non il prezzo.", size=8.5, colore=cp.TESTO_SOFT)

    pdf.add_page()
    pdf.sezione("Nel tempo e nei mesi")
    pdf.image(grafico_cassa(d["cassa"], d["orizzonte"]), w=172)
    pdf.ln(1)
    pdf.image(grafico_mensile(d["mensile"]), w=172)

    pdf.sezione("Ipotesi di calcolo")
    pdf.elenco(d["ipotesi"])

    pdf.sezione("Avvertenze")
    pdf.testo(d["avvertenze"], size=8.5, colore=cp.TESTO_SOFT)
    return bytes(pdf.output())
