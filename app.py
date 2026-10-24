"""Verifica dimensionamento FV + accumulo da curve del Portale Consumi ARERA.

Avvio:  streamlit run app.py
Il CSV caricato resta in memoria nella sessione: non viene scritto su disco.
Parametri standard (costi, prezzi, incentivi...) in parametri.toml.
"""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image

from engine import config, finanza, geocode, giudizio, parser, profili, pv, report, sim

# palette climaction
import stile
from stile import BLU, MODELLI, NEUTRO, OCRA, ROSSO, STAGIONI, VERDE, VERDE_CH
MESI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
ALTRO = "Altro (coordinate)"
ROOT = Path(__file__).resolve().parent

_ICONA = ROOT / "assets" / "logo_climaction.png"
st.set_page_config(page_title="Fotovoltaico e batteria · climaction", layout="wide",
                   page_icon=Image.open(_ICONA) if _ICONA.exists() else None,
                   initial_sidebar_state="collapsed")
stile.applica()


# ================================================================ utilità
def num(x, dec=0):
    """Formato italiano: 1.234,5"""
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def validita(inc):
    """Testo del periodo di validità di un incentivo, es. ' (valido dal 01/01/2026 al 31/12/2026)'."""
    dal, al = inc.get("valido_dal"), inc.get("valido_al")
    al_t = f"al {al:%d/%m/%Y}" if al else inc.get("valido_al_testo", "")
    if dal and al_t:
        return f" (valido dal {dal:%d/%m/%Y} {al_t})"
    if dal:
        return f" (valido dal {dal:%d/%m/%Y})"
    return f" (valido {al_t})" if al_t else ""


def anni(x):
    return f"{num(x, 0)} anni" if np.isfinite(x) else "oltre la vita utile"


def style(fig, h=380, ytitle=None):
    fig.update_layout(height=h, hovermode="x unified")  # resto dal template "climaction" (stile.py)
    if ytitle:
        fig.update_layout(yaxis_title=ytitle)
    return fig


@st.cache_data(show_spinner=False)
def cfg_cached(_mtime):  # la cache si invalida quando il file cambia
    return config.load_config()


@st.cache_data(show_spinner="Cerco il comune...", ttl=86400, max_entries=200)
def cerca_cached(q):
    return geocode.cerca(q)


@st.cache_data(show_spinner="Lettura della curva di consumo...", max_entries=3)
def load_cached(b: bytes):
    return parser.build_load_year(b)


@st.cache_data(show_spinner="Scarico la produzione solare da PVGIS...", max_entries=20)
def pv_cached(lat, lon, angle, orient, loss, y0, y1):
    prof = pv.pv_profiles(lat, lon, angle, orient, loss, y0, y1)
    return prof, pv.pick_years(prof)


@st.cache_data(show_spinner="Simulo un anno di funzionamento per ogni configurazione...", max_entries=30)
def scan_cached(load, pv1, kwp_list, kwh_list, dod, eta, crate, pmin, lim):
    return sim.scan(load, pv1, list(kwp_list), list(kwh_list), sim.Battery(0, dod, eta, crate, pmin), lim)


@st.cache_data(show_spinner="Preparo il PDF...", max_entries=10)
def pdf_cached(d):
    return report.genera_pdf(d, LOGO_PNG)


def footer():
    st.divider()
    c1, c2 = st.columns([1, 14], vertical_alignment="center")
    if LOGO_PNG:
        c1.markdown(stile.logo_html(SITO, LOGO_PNG, 56), unsafe_allow_html=True)
    c2.markdown(f"**climaction** · {CFG['app']['firma']} · "
                f"[Come funziona lo strumento]({CFG['app']['url_istruzioni']})  \n"
                "Strumento per abitazioni private. "
                f"Costi e prezzi standard aggiornati a {CFG['meta']['aggiornamento']}. "
                "Le stime hanno un'incertezza indicativa del 10–20%.")


# ================================================================ configurazione e valori di default
try:
    CFG = cfg_cached(config.mtime())
except Exception as e:  # noqa: BLE001
    st.error(f"Errore nel file parametri.toml: {e}")
    st.stop()
B, FV, AN, CO, EN, FZ = (CFG[k] for k in ("batteria", "fv", "analisi", "costi", "energia", "finanza"))
INC = CFG["incentivi"]
COMUNI = {k: tuple(v) for k, v in CFG["comuni"].items()} | {ALTRO: None}
SITO = CFG["app"].get("url_sito", "https://climaction.it/")
LOGO_PNG = stile.carica_logo(ROOT / CFG["app"]["logo"])

# parametri avanzati: valori standard da parametri.toml
DEF = {
    "adv_fv_eur": float(CO["fv_eur_kwp"]), "adv_batt_eur": float(CO["batteria_eur_kwh"]),
    "adv_batt_fisso": float(CO["batteria_fisso_eur"]), "adv_manut": float(CO["manutenzione_eur_kwp_anno"]),
    "adv_prezzo": float(EN["prezzo_prelievo"]), "adv_immesso": float(EN["valore_immissione"]),
    "adv_tasso": float(FZ["tasso_sconto"] * 100), "adv_infl": float(FZ["inflazione_energia"] * 100),
    "adv_orizzonte": int(FZ["orizzonte_anni"]), "adv_degrado": float(FZ["degrado_fv"] * 100),
    "adv_vita_batt": int(FZ["vita_batteria_anni"]), "adv_sost": int(FZ["costo_sostituzione"] * 100),
    "adv_dod": int(B["dod"] * 100), "adv_eta": int(B["rendimento"] * 100),
    "adv_crate": float(B["c_rate"]), "adv_pmin": float(B["potenza_min_kw"]),
    "adv_perdite": int(FV["perdite"]), "adv_meteo": "mediana",
    "adv_incl_on": False, "adv_incl": int(FV["inclinazione_falda"]),
    "adv_lim": False, "adv_libera": False, "adv_kwp": 4.0, "adv_kwh": 5.0,
}
LEVE = {"superficie": 0, "incentivo": next(iter(INC)), "val_rientro": 10, "val_aut": 0.6,
        "obiettivo": "guadagno"}
for k, v in {**DEF, **LEVE}.items():
    st.session_state.setdefault(k, v)
S = st.session_state


def ripristina():
    for k, v in DEF.items():
        S[k] = v


modificati = [k for k, v in DEF.items() if S[k] != v]

# ================================================================ intestazione
h0, h1, h2 = st.columns([0.7, 8, 2.3], vertical_alignment="center")
if LOGO_PNG:
    h0.markdown(stile.logo_html(SITO, LOGO_PNG, 68), unsafe_allow_html=True)
else:
    st.warning(f"Logo non trovato: metti il file in {CFG['app']['logo']} (percorso indicato in parametri.toml).")
h1.title("Fotovoltaico e batteria: quanto ti serve?")
h2.link_button("Come funziona", CFG["app"]["url_istruzioni"], width="stretch")
st.caption("Strumento pensato per **abitazioni private** (utenze domestiche di persone fisiche). "
           "Non è adatto a imprese, condomini, enti pubblici o del terzo settore: incentivi, IVA e "
           "fiscalità sono diversi e i risultati non sarebbero corretti.")

# ================================================================ 1. dati
st.subheader("1 · I tuoi dati")
c1, c2, c3 = st.columns(3, gap="large")
MODI = ["Carico il file del Portale Consumi", "Ho le fasce F1/F2/F3 della bolletta", "Indico solo il consumo annuo"]
MESI_LUNGHI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
               "settembre", "ottobre", "novembre", "dicembre"]
PRES_TXT = {"quasi mai": "Quasi mai (tutti fuori casa)", "a volte": "A volte",
            "sempre": "Quasi sempre (smart working, pensionati...)"}
with c1:
    modo = st.radio("Come vuoi dirmi i tuoi consumi?", MODI, key="modo",
                    help="Il file del Portale Consumi è la strada più precisa. Le altre due costruiscono "
                         "un profilo stimato: sono più veloci ma più incerte.")
    up = None
    if modo == MODI[0]:
        up = st.file_uploader("Curva di consumo quartoraria (CSV dal Portale Consumi ARERA)", type=["csv"])
        st.caption("Il file viene elaborato solo in memoria per il calcolo e non viene salvato.")
    elif modo == MODI[1]:
        cc = st.columns(3)
        f1_in = cc[0].number_input("F1 [kWh/anno]", 0, 40000, 0, 50)
        f2_in = cc[1].number_input("F2 [kWh/anno]", 0, 40000, 0, 50)
        f3_in = cc[2].number_input("F3 [kWh/anno]", 0, 40000, 0, 50)
        mensili_in = None
        if st.toggle("Ho anche i consumi mensili (più preciso)"):
            ed = st.data_editor(pd.DataFrame({"Mese": MESI_LUNGHI, "kWh": [0.0] * 12}), hide_index=True,
                                disabled=["Mese"], height=460,
                                column_config={"kWh": st.column_config.NumberColumn(min_value=0.0, step=10.0)})
            if ed["kWh"].sum() > 0:
                mensili_in = ed["kWh"].tolist()
        st.caption("Li trovi in bolletta o nell'area clienti del fornitore. Meglio se sono gli ultimi 12 mesi.")
    else:
        kwh_in = st.number_input("Consumo annuo [kWh]", 300, 20000, 2700, 100)
        pres_in = st.radio("Di giorno in casa c'è qualcuno?", list(PRES_TXT), index=1,
                           format_func=PRES_TXT.get, horizontal=True)
        pdc_in = st.checkbox("Riscaldo la casa con la pompa di calore")
    aiuto_consumi = st.empty()
with c2:
    ricerca = st.text_input("Comune", value="Novara", help="Scrivi il nome del comune e premi Invio.")
    manuale = st.toggle("Inserisci le coordinate a mano")
    if manuale:
        cc = st.columns(2)
        lat = cc[0].number_input("Latitudine", value=45.446, format="%.4f")
        lon = cc[1].number_input("Longitudine", value=8.622, format="%.4f")
        comune = f"{lat:.4f}, {lon:.4f}"
    else:
        try:
            trovati = cerca_cached(ricerca)
        except Exception:  # noqa: BLE001
            trovati = None
            st.error("Il servizio di ricerca dei comuni non risponde. Riprova tra poco "
                     "oppure inserisci le coordinate a mano.")
        if trovati == []:
            st.warning("Nessun comune trovato: controlla il nome o inserisci le coordinate a mano.")
        if not trovati:
            st.stop()
        scelta = st.selectbox("Conferma la località", trovati, format_func=geocode.etichetta)
        lat, lon = scelta["lat"], scelta["lon"]
        comune = geocode.etichetta(scelta)
        st.caption(f"{comune} · {abs(lat):.3f}° {'N' if lat >= 0 else 'S'}, "
                   f"{abs(lon):.3f}° {'E' if lon >= 0 else 'O'}")
    orient = st.selectbox("Orientamento del tetto", list(pv.ORIENTAMENTI))
    tetto = st.radio("Tipo di tetto", ["A falda", "Piano"], horizontal=True)
with c3:
    cont = st.selectbox("Potenza del contatore", ["3 kW", "4,5 kW", "6 kW", "Altro", "Non so"], index=4,
                        help="La trovi in bolletta come 'potenza impegnata'.")
    if cont == "Altro":
        p_imp = st.number_input("Potenza impegnata [kW]", 1.0, 30.0, 10.0, 0.5)
    elif cont == "Non so":
        p_imp = None
    else:
        p_imp = float(cont.split()[0].replace(",", "."))
    if p_imp is None and modo != MODI[0]:
        st.caption("Senza il file non posso stimarla dai picchi: assumo 3 kW.")
    prev = st.toggle("Ho già un preventivo da verificare")
    if prev:
        cc = st.columns(2)
        prev_kwp = cc[0].number_input("Fotovoltaico [kW]", 1.0, 20.0, 6.0, 0.1)
        prev_kwh = cc[1].number_input("Batteria [kWh]", 0.0, 40.0, 10.0, 0.5)

regione_nome = None if manuale else scelta.get("regione", "")
reg_arera = profili.regione_arera(regione_nome)
if modo == MODI[1]:
    q = profili.quote_fasce_tipiche(reg_arera, "3_a_4_5")
    aiuto_consumi.caption(
        f"Per riferimento: un'abitazione con contatore da 3 kW {('in ' + reg_arera) if reg_arera else 'in Italia'} "
        f"ha in media il {q[0]:.0%} dei consumi in F1, il {q[1]:.0%} in F2 e il {q[2]:.0%} in F3 (ARERA, 2025).")
elif modo == MODI[2]:
    t = profili.consumo_tipico(reg_arera)
    aiuto_consumi.caption(
        f"Per riferimento, consumo medio annuo di un'abitazione residente {('in ' + reg_arera) if reg_arera else 'in Italia'} "
        "con contatore da " + "; ".join(f"{profili.CLASSE_ETICHETTA[c]}: {num(v)} kWh" for c, v in t.items())
        + " (ARERA, 2025).")

stima = None
if modo == MODI[0]:
    if up is None:
        st.info("Per iniziare carica il file con i tuoi consumi. Le istruzioni per scaricarlo dal "
                f"Portale Consumi sono nella [pagina di istruzioni su climaction.it]({CFG['app']['url_istruzioni']}). "
                "Se non vuoi o non puoi scaricarlo, scegli un'altra opzione qui sopra.")
        footer()
        st.stop()
    try:
        load, daily, rep = load_cached(up.getvalue())
    except Exception as e:  # noqa: BLE001
        st.error(f"Impossibile leggere il file: {e}")
        st.stop()
else:
    try:
        if modo == MODI[1]:
            if f1_in + f2_in + f3_in <= 0:
                st.info("Inserisci i kWh annui delle tre fasce F1, F2 e F3 per iniziare.")
                footer()
                st.stop()
            stima = profili.da_fasce(f1_in, f2_in, f3_in, mensili=mensili_in, regione=regione_nome)
        else:
            stima = profili.da_consumo_annuo(kwh_in, regione=regione_nome, presenza=pres_in, pompa_calore=pdc_in)
    except ValueError as e:
        st.error(f"Dati non validi: {e}")
        st.stop()
    load, daily = stima.serie, None
    rep = parser.LoadReport(pod="", righe_file=0, duplicati_rimossi=0, giorni_validi=365,
                            finestra_inizio=load.index[0], finestra_fine=load.index[-1], avvisi=stima.avvisi)
    st.info("**Profilo di consumo stimato.** Non avendo la tua curva, la ricostruisco dai dati ARERA sui "
            "consumi domestici della tua regione, adattati ai kWh che indichi. I risultati su autonomia e "
            f"rientro sono quindi più incerti ({stima.incertezza}). Per un calcolo più preciso carica il file "
            "del Portale Consumi.")
    for a in stima.avvisi:
        st.caption("• " + a)

angle = S.adv_incl if S.adv_incl_on else int(FV["inclinazione_falda"] if tetto == "A falda" else FV["inclinazione_piano"])
try:
    profiles, yrs = pv_cached(lat, lon, angle, orient, S.adv_perdite,
                              int(FV["pvgis_anno_inizio"]), int(FV["pvgis_anno_fine"]))
except Exception as e:  # noqa: BLE001
    st.error(f"Il servizio PVGIS non risponde ({e}). Riprova tra qualche minuto.")
    st.stop()
pv1 = profiles[yrs[S.adv_meteo]]

if stima is None:
    picco, p_stimata = giudizio.potenza_contatore_stimata(load)
    p_cont = p_imp if p_imp else p_stimata
else:  # profilo stimato: i picchi reali non si vedono, la potenza non si deduce da qui
    picco, p_stimata = float(load.max() * 4), None
    p_cont = p_imp if p_imp else 3.0
lim = p_cont * 1.1 if S.adv_lim else 0.0
dod, eta, crate, pmin = S.adv_dod / 100, S.adv_eta / 100, S.adv_crate, S.adv_pmin
passo = float(AN["passo_batteria_kwh"])
kwh_list = tuple(np.round(np.arange(0, float(AN["batteria_max_kwh"]) + 1e-9, passo), 2))
kwp_list = tuple(np.round(np.arange(1.5, float(FV["kwp_max_base"]) + 1e-9, 0.5), 2))
grid = scan_cached(load, pv1, kwp_list, kwh_list, dod, eta, crate, pmin, lim)
consumo = load.sum()
batt_tpl = sim.Battery(0, dod, eta, crate, pmin)

# ================================================================ 2. obiettivo
st.subheader("2 · Cosa ti aspetti dall'impianto?")
st.radio("Obiettivo", list(finanza.OBIETTIVI), format_func=finanza.OBIETTIVI.get, key="obiettivo",
         label_visibility="collapsed", captions=[
             "Spendi il giusto per riavere indietro i soldi nel minor tempo.",
             "Il guadagno complessivo più alto sulla vita dell'impianto, anche se rientri più tardi.",
             "Scegli in quanti anni vuoi rientrare: cerchiamo l'impianto più autonomo che ci sta dentro.",
             "Scegli quanta parte dei consumi vuoi coprire col sole: cerchiamo la soluzione meno costosa.",
         ])

# ================================================================ calcolo
inc = INC[S.incentivo]
f = finanza.Finanza(
    prezzo_prelievo=S.adv_prezzo, valore_immissione=S.adv_immesso, costo_fv_kwp=S.adv_fv_eur,
    costo_batt_kwh=S.adv_batt_eur, costo_batt_fisso=S.adv_batt_fisso,
    incentivo_pct=float(inc["percentuale"]), incentivo_rate=int(inc.get("rate", 1)),
    massimale_spesa=inc.get("massimale_spesa") or None, massimale_fv_kwp=inc.get("massimale_fv_kwp") or None,
    massimale_batt_kwh=inc.get("massimale_batt_kwh") or None, orizzonte=int(S.adv_orizzonte),
    tasso_sconto=S.adv_tasso / 100, inflazione_energia=S.adv_infl / 100, degrado_fv=S.adv_degrado / 100,
    manutenzione_kwp=S.adv_manut, vita_batteria=int(S.adv_vita_batt), sostituzione_frac=S.adv_sost / 100)

kwp_cap = float(FV["kwp_max_base"])
if S.superficie > 0:
    kwp_cap = min(kwp_cap, np.floor(S.superficie / FV["m2_per_kwp"] * 2) / 2)
g_ok = grid[grid["kwp"] <= kwp_cap + 1e-9]


def riga(kwp, kwh):
    """Indicatori tecnici ed economici per una configurazione qualsiasi."""
    r = sim.simulate(load, pv1, kwp, sim.Battery(kwh, dod, eta, crate, pmin), lim_kw=lim)
    cf = finanza.flussi(r, consumo, f)
    tot = finanza.incentivo_totale(kwp, kwh, f)
    return pd.Series({**r, **finanza.indicatori(cf, f.tasso_sconto), "incentivo": tot, "netto": -cf[0] - tot})


val = {"rientro_entro": S.val_rientro, "autonomia": S.val_aut}.get(S.obiettivo)
avviso_ob = None
if S.adv_libera:
    best = riga(S.adv_kwp, S.adv_kwh)
    e = finanza.valuta(grid, consumo, f)
elif g_ok.empty:
    best = None
else:
    e = finanza.valuta(g_ok, consumo, f)
    best, avviso_ob = finanza.scegli(e, S.obiettivo, val)

# ================================================================ 3. risultato
st.subheader("3 · La soluzione proposta" if not S.adv_libera else "3 · La configurazione che hai scelto")
if modificati:
    w1, w2 = st.columns([5, 1], vertical_alignment="center")
    w1.warning(f"Stai usando {len(modificati)} " + ("parametro diverso" if len(modificati) == 1 else "parametri diversi")
               + " da quelli standard "
               "(vedi Parametri avanzati in fondo alla pagina).")
    w2.button("Ripristina", on_click=ripristina, width="stretch")
if avviso_ob:
    st.warning(avviso_ob)

if best is None:
    st.error(f"Con {S.superficie} m² ci stanno meno di 1,5 kW di pannelli: troppo pochi per una "
             "valutazione sensata. Modifica la superficie qui sotto.")
else:
    kwp, kwh = float(best["kwp"]), float(best["kwh"])
    with st.container(border=True):
        st.markdown(f"#### {num(kwp, 1)} kW di fotovoltaico"
                    + (f" + batteria da {num(kwh, 1)} kWh" if kwh > 0 else ", senza batteria"))
        c = st.columns(5)
        c[0].metric("Consumi coperti dal sole", f"{best['autosufficienza']:.0%}")
        c[1].metric("Risparmio il primo anno", f"{num(best['risparmio_primo_anno'])} €")
        c[2].metric("Spesa al netto incentivi", f"{num(best['netto'])} €")
        c[3].metric("Rientro", anni(best["payback_att"]))
        c[4].metric(f"Guadagno in {f.orizzonte} anni", f"{num(best['van'])} €",
                    help="Valore attuale netto: quanto guadagni in totale, in euro di oggi.")
    st.caption("Calcolo economico semplificato: le voci considerate e quelle escluse sono in "
               "Approfondimenti → Ipotesi di calcolo.")
    if kwp > p_cont:
        st.info(f"L'impianto da {num(kwp, 1)} kW supera la potenza del contatore "
                f"({num(p_cont, 1)} kW{(' stimati dai tuoi consumi' if stima is None else ' assunti') if p_imp is None else ''}): ricordati di "
                "chiedere con l'installatore l'adeguamento della potenza in immissione al distributore, "
                "insieme alla pratica di connessione.")
    if best.get("tagliata", 0) > 1:
        st.caption(f"Con il limite di immissione si perdono circa {num(best['tagliata'])} kWh all'anno.")

# ---- leve
with st.container(border=True):
    st.markdown("**Affina la proposta**")
    lc = st.columns(3)
    with lc[0]:
        if S.obiettivo == "rientro_entro":
            st.select_slider("Rientro entro", [5, 6, 7, 8, 10, 12, 15], key="val_rientro",
                             format_func=lambda x: f"{x} anni")
        elif S.obiettivo == "autonomia":
            st.select_slider("Autonomia desiderata", [0.4, 0.5, 0.6, 0.7, 0.8], key="val_aut",
                             format_func=lambda x: f"{x:.0%} dei consumi")
        else:
            st.caption(f"Obiettivo: {finanza.OBIETTIVI[S.obiettivo].lower()}. Puoi cambiarlo al punto 2.")
    lc[1].number_input("Superficie libera sul tetto [m²]", 0, 500, step=5, key="superficie",
                       help=f"0 = non la conosco. Servono circa {num(FV['m2_per_kwp'], 1)} m² per kW.")
    with lc[2]:
        st.selectbox("Incentivo", list(INC), format_func=lambda k: INC[k]["nome"], key="incentivo")
    st.caption(f"{inc['nome']}: {inc['percentuale']:.0%} della spesa"
               + (f", in {inc['rate']} rate annuali" if inc.get("rate", 1) > 1 else "")
               + validita(inc) + ". " + inc["descrizione"])
    if inc.get("valido_al") and date.today() > inc["valido_al"]:
        st.error(f"Il periodo di validità indicato per questo incentivo è terminato il "
                 f"{inc['valido_al']:%d/%m/%Y}: il valore potrebbe non essere più aggiornato.")
    if inc.get("avviso"):
        st.warning(inc["avviso"])

if best is not None:
    # ---- confronto con lo stesso FV
    same = finanza.valuta(grid[np.isclose(grid["kwp"], kwp)], consumo, f).set_index("kwh", drop=False) \
        if not S.adv_libera or kwp in kwp_list else None
    alt = [("Proposta" if not S.adv_libera else "La tua scelta", best)]
    if same is not None:
        if kwh > 0:
            alt.append(("Senza batteria", same.loc[0.0]))
        else:
            k = sim.knee(grid[np.isclose(grid["kwp"], kwp)], float(AN["soglia_ginocchio"]))["kwh_ginocchio"].iloc[0] or passo
            alt.append(("Con batteria", same.loc[k]))
        up_k = [x for x in same.index if x > max(kwh, alt[-1][1]["kwh"])]
        if up_k:
            alt.append(("Batteria più grande", same.loc[up_k[min(1, len(up_k) - 1)]]))
        st.markdown("**A confronto, con lo stesso impianto fotovoltaico**")
        st.dataframe(pd.DataFrame({
            "": [n for n, _ in alt],
            "Batteria [kWh]": [num(r["kwh"], 1) for _, r in alt],
            "Consumi coperti": [f"{r['autosufficienza']:.0%}" for _, r in alt],
            "Spesa netta [€]": [num(r["netto"]) for _, r in alt],
            "Rientro": [anni(r["payback_att"]) for _, r in alt],
            f"Guadagno {f.orizzonte} anni [€]": [num(r["van"]) for _, r in alt],
        }), hide_index=True, width="stretch")

    # ---- preventivo
    if prev:
        st.markdown("#### Il tuo preventivo")
        gv = giudizio.valuta_preventivo(
            load, pv1, prev_kwp, prev_kwh, kwh_list, batt_tpl, float(AN["soglia_ginocchio"]),
            kwp_cap if S.superficie > 0 else None, lim,
            CFG["giudizio"]["produzione_bassa"], CFG["giudizio"]["produzione_alta"])
        livello = {"adeguato": 0, "adeguata": 0, "piccolo": 3, "piccola": 3, "grande": 3, "assente": None}
        c = st.columns(2)
        with c[0]:
            stile.badge(f"Fotovoltaico {num(prev_kwp, 1)} kW", gv["fv"], livello[gv["fv"]])
        with c[1]:
            stile.badge(f"Batteria {num(prev_kwh, 1)} kWh", gv["batteria"], livello[gv["batteria"]])
        for m in gv["messaggi"]:
            st.markdown(f"- {m}")
        rp = gv["r"]
        st.dataframe(pd.DataFrame({
            "": ["Preventivo", alt[0][0]],
            "FV [kW]": [num(prev_kwp, 1), num(kwp, 1)],
            "Batteria [kWh]": [num(prev_kwh, 1), num(kwh, 1)],
            "Consumi coperti": [f"{rp['autosufficienza']:.0%}", f"{best['autosufficienza']:.0%}"],
            "Produzione usata in casa": [f"{rp['autoconsumo']:.0%}", f"{best['autoconsumo']:.0%}"],
            "Energia in rete [kWh/anno]": [num(rp["immissione"]), num(best["immissione"])],
            "Giorni a batteria piena": [int(rp["giorni_piena"]), int(best["giorni_piena"])],
        }), hide_index=True, width="stretch")
        st.caption("Il giudizio riguarda solo il dimensionamento. Non valutiamo il prezzo: un preventivo "
                   "comprende voci (ponteggi, pratiche, garanzie, componenti) che qui non conosciamo.")

    # ================================================================ 4. grafici
    st.subheader("4 · Nel tempo e nei mesi")
    _, df = sim.simulate(load, pv1, kwp, sim.Battery(kwh, dod, eta, crate, pmin), detail=True, lim_kw=lim)
    g1, g2 = st.columns(2)
    with g1:
        fig = go.Figure()
        ax = np.arange(f.orizzonte + 1)
        curve = []
        for (nome, r), col in zip(alt, [VERDE, NEUTRO, BLU]):
            cf = finanza.flussi(r.to_dict(), consumo, f)
            cum = np.cumsum(cf / (1 + f.tasso_sconto) ** ax)
            curve.append((nome, [float(x) for x in cum]))
            fig.add_scatter(x=ax, y=cum, name=nome, line=dict(color=col, width=3 if r is best else 2))
        fig.add_hline(y=0, line=dict(color=NEUTRO, width=1))
        fig.update_layout(title="Soldi spesi e recuperati (euro di oggi)")
        fig.update_xaxes(title="anni")
        st.plotly_chart(style(fig, h=380, ytitle="€"), width="stretch")
        st.caption("La curva parte dalla spesa iniziale e risale con i risparmi in bolletta e le rate "
                   "dell'incentivo: dove incrocia lo zero sei rientrato. Il gradino è la sostituzione della batteria.")
    with g2:
        mm = df.groupby(df.index.month)[["fv_diretto", "scarica", "prelievo", "fv"]].sum()
        fig = go.Figure()
        fig.add_bar(x=MESI, y=mm["fv_diretto"], name="Dal sole, subito", marker_color=VERDE)
        fig.add_bar(x=MESI, y=mm["scarica"], name="Dalla batteria", marker_color=VERDE_CH)
        fig.add_bar(x=MESI, y=mm["prelievo"], name="Dalla rete", marker_color=MODELLI)
        fig.add_scatter(x=MESI, y=mm["fv"], name="Produzione FV", mode="lines+markers",
                        line=dict(color=OCRA, width=2, dash="dot"))
        fig.update_layout(barmode="stack", title="Come vengono coperti i tuoi consumi, mese per mese")
        st.plotly_chart(style(fig, h=380, ytitle="kWh/mese"), width="stretch")
        st.caption("D'inverno il sole copre poco anche con la batteria: è il limite di ogni impianto domestico.")

    ipotesi = [
        f"Costi: FV {num(f.costo_fv_kwp)} €/kW, batteria {num(f.costo_batt_kwh)} €/kWh + "
        f"{num(f.costo_batt_fisso)} € fissi, manutenzione {num(f.manutenzione_kwp)} €/kW all'anno "
        f"(aggiornati a {CFG['meta']['aggiornamento']}).",
        f"Energia prelevata {num(f.prezzo_prelievo, 2)} €/kWh, immessa in rete {num(f.valore_immissione, 2)} €/kWh; "
        f"prezzi in crescita del {num(f.inflazione_energia * 100, 1)}% all'anno.",
        f"Incentivo: {inc['nome']}, {f.incentivo_pct:.0%}"
        + (f" in {f.incentivo_rate} rate annuali" if f.incentivo_rate > 1 else "") + validita(inc) + ".",
        f"Flussi futuri attualizzati al {num(f.tasso_sconto * 100, 1)}% annuo: un euro tra 10 anni vale meno "
        "di un euro oggi.",
        f"I pannelli perdono il {num(f.degrado_fv * 100, 1)}% di produzione all'anno; la batteria si sostituisce "
        f"dopo {f.vita_batteria} anni al {f.sostituzione_frac:.0%} del costo di oggi.",
        f"Batteria: capacità utile {dod:.0%}, rendimento {eta:.0%}, carica solo dal fotovoltaico.",
        f"Produzione da PVGIS (Commissione europea), anno meteo {S.adv_meteo}; consumi dal file del Portale "
        "Consumi, simulati quarto d'ora per quarto d'ora su un anno.",
    ]
    non_considerati = [
        "finanziamento: interessi di un mutuo o di un prestito (l'investimento è pagato in contanti)",
        "sostituzione dell'inverter (di solito dopo 10–15 anni) e calo di capacità della batteria negli anni",
        "prezzo dell'energia per fasce orarie e quote fisse della bolletta: si usa un prezzo medio per kWh",
        "capienza IRPEF: si assume che la detrazione venga recuperata per intero",
        "costi di connessione o di adeguamento del contatore",
        "ricavi da una comunità energetica (CER) e oscillazioni future dei prezzi oltre la crescita costante",
    ]
    nota_economica = ("Il calcolo economico è semplificato. Alcune voci escluse renderebbero il rientro più "
                      "lungo (inverter, finanziamento, detrazione non recuperata per intero), altre più breve "
                      "(ricavi da comunità energetica, prezzi dell'energia in crescita più rapida). "
                      "Il rientro indicato è attualizzato, quindi più prudente di un semplice rapporto "
                      "spesa/risparmio.")

    # ---- esportazione PDF
    luogo = comune
    ob_txt = finanza.OBIETTIVI[S.obiettivo]
    if S.obiettivo == "rientro_entro":
        ob_txt += f" ({S.val_rientro} anni)"
    elif S.obiettivo == "autonomia":
        ob_txt += f" ({S.val_aut:.0%})"
    dati_pdf = [
        ("Località", luogo),
        ("Tetto", f"{orient}, {tetto.lower()}, inclinazione {angle}°"),
        ("Consumo annuo", (f"{num(consumo)} kWh (profilo stimato: {stima.descrizione})" if stima is not None
                           else f"{num(consumo)} kWh (dati dal {rep.finestra_inizio:%d/%m/%Y} al "
                                f"{rep.finestra_fine:%d/%m/%Y}, {rep.giorni_validi} giorni misurati)")),
        ("Produzione FV specifica", f"{num(pv1.sum())} kWh per kW all'anno (PVGIS, anno meteo {S.adv_meteo})"),
        ("Potenza del contatore", f"{num(p_cont, 1)} kW" + ((" (stimata dai consumi)" if stima is None else " (assunta)") if p_imp is None else "")),
        ("Superficie libera sul tetto", f"{S.superficie} m²" if S.superficie else "non indicata"),
        ("Incentivo", f"{inc['nome']}, {inc['percentuale']:.0%}" + validita(inc)),
        ("Obiettivo", "configurazione scelta dall'utente" if S.adv_libera else ob_txt),
    ]
    if modificati:
        dati_pdf.append(("Parametri avanzati", f"{len(modificati)} valori diversi da quelli standard"))
    avvisi_pdf = [x for x in [avviso_ob, inc.get("avviso") or None] if x]
    if stima is not None:
        avvisi_pdf.append(f"Profilo di consumo stimato, non misurato ({stima.incertezza}). Autonomia, "
                          "autoconsumo e rientro sono più incerti rispetto a un calcolo con la curva del "
                          "Portale Consumi.")
    if kwp > p_cont:
        avvisi_pdf.append(f"L'impianto supera la potenza del contatore ({num(p_cont, 1)} kW): va chiesto "
                          "l'adeguamento della potenza in immissione al distributore.")
    d_pdf = {
        "firma": CFG["app"]["firma"], "sito": SITO.replace("https://", "").rstrip("/"),
        "aggiornamento": CFG["meta"]["aggiornamento"], "orizzonte": f.orizzonte,
        "dati": dati_pdf,
        "titolo_risultato": "La configurazione scelta" if S.adv_libera else "La soluzione proposta",
        "configurazione": f"{num(kwp, 1)} kW di fotovoltaico"
                          + (f" + batteria da {num(kwh, 1)} kWh" if kwh > 0 else ", senza batteria"),
        "metriche": [("Consumi coperti dal sole", f"{best['autosufficienza']:.0%}"),
                     ("Risparmio il primo anno", f"{num(best['risparmio_primo_anno'])} €"),
                     ("Spesa al netto incentivi", f"{num(best['netto'])} €"),
                     ("Rientro", anni(best["payback_att"])),
                     (f"Guadagno in {f.orizzonte} anni", f"{num(best['van'])} €")],
        "dettagli": [("Investimento", f"{num(best['investimento'])} € (incentivo {num(best['incentivo'])} €)"),
                     ("Produzione annua", f"{num(best['produzione'])} kWh, di cui usata in casa il "
                                          f"{best['autoconsumo']:.0%}"),
                     ("Energia dalla rete / in rete", f"{num(best['prelievo'])} / {num(best['immissione'])} kWh all'anno"),
                     ("Batteria", f"{best['cicli']:.0f} cicli all'anno" if kwh > 0 else "assente")],
        "avvisi": avvisi_pdf,
        "confronto": (["", "Batteria kWh", "Consumi coperti", "Spesa netta €", "Rientro", f"Guadagno {f.orizzonte} anni €"],
                      [[n, num(r["kwh"], 1), f"{r['autosufficienza']:.0%}", num(r["netto"]),
                        anni(r["payback_att"]), num(r["van"])] for n, r in alt]) if len(alt) > 1 else None,
        "preventivo": {"giudizi": [(f"Fotovoltaico {num(prev_kwp, 1)} kW", gv["fv"]),
                                   (f"Batteria {num(prev_kwh, 1)} kWh", gv["batteria"])],
                       "messaggi": gv["messaggi"]} if prev else None,
        "cassa": curve,
        "mensile": {k: [float(x) for x in mm[k]] for k in ("fv_diretto", "scarica", "prelievo", "fv")},
        "ipotesi": ipotesi + ["Non considerati: " + "; ".join(non_considerati) + ".", nota_economica],
        "avvertenze": "Stima indicativa (incertezza del 10–20%) basata sui consumi di un anno e su dati "
                      "meteo storici; non sostituisce il progetto di un tecnico abilitato. Strumento pensato "
                      "per abitazioni private: per imprese, condomini ed enti incentivi e fiscalità sono diversi. "
                      "Il file dei consumi è stato elaborato solo in memoria e non è stato salvato.",
    }
    pdf_bytes = pdf_cached(d_pdf)
    st.download_button("Esporta in PDF", data=pdf_bytes, type="primary", icon=":material/picture_as_pdf:",
                       file_name=f"verifica_fotovoltaico_{date.today():%Y%m%d}.pdf", mime="application/pdf",
                       help="Riepilogo con dati di partenza, risultati, grafici e ipotesi di calcolo.")

    # ================================================================ 5. approfondimenti
    st.subheader("5 · Approfondimenti")
    with st.expander("Tutte le alternative: rientro e autonomia a confronto"):
        ee = e.copy()
        ee["pb"] = ee["payback_att"].clip(upper=f.orizzonte + 1)
        fig = go.Figure()
        col_b = stile.rampa(ee["kwh"].nunique())
        for i, (kb, gk) in enumerate(ee.groupby("kwh")):
            fig.add_scatter(x=gk["pb"], y=gk["autosufficienza"] * 100, mode="markers",
                            name=f"{kb:g} kWh", marker=dict(size=7 + gk["kwp"], color=col_b[i], opacity=0.85,
                                                                           line=dict(color="white", width=0.5)),
                            customdata=gk[["kwp", "netto"]],
                            hovertemplate="%{customdata[0]} kW + " + f"{kb:g} kWh" +
                                          "<br>rientro %{x:.1f} anni<br>autonomia %{y:.0f}%<extra></extra>")
        fig.add_scatter(x=[min(best["payback_att"], f.orizzonte + 1)], y=[best["autosufficienza"] * 100],
                        mode="markers", name="Proposta",
                        marker=dict(symbol="star", size=22, color=ROSSO, line=dict(color="white", width=1)))
        if S.obiettivo == "rientro_entro" and not S.adv_libera:
            fig.add_vline(x=S.val_rientro, line=dict(color=ROSSO, dash="dash"))
        if S.obiettivo == "autonomia" and not S.adv_libera:
            fig.add_hline(y=S.val_aut * 100, line=dict(color=ROSSO, dash="dash"))
        fig.update_layout(title="Ogni punto è una configurazione (colore = batteria, grandezza = kW di FV)")
        fig.update_xaxes(title=f"anni per rientrare (a destra: oltre {f.orizzonte} anni)")
        st.plotly_chart(style(fig, h=460, ytitle="consumi coperti dal sole [%]").update_layout(hovermode="closest"),
                        width="stretch")
        st.caption("Non si può avere tutto: le configurazioni che rientrano prima coprono pochi consumi, quelle "
                   "molto autonome costano di più e rientrano più tardi. Verso l'alto le curve si fermano: "
                   "d'inverno il sole non basta e la batteria non sposta energia dall'estate all'inverno.")

    with st.expander("Come lavora la batteria"):
        if kwh > 0:
            cap = kwh * dod
            sd = df["soc"].to_numpy().reshape(365, 96)
            pm = pd.DataFrame({"piena": sd.max(1) >= 0.98 * cap, "vuota": sd.min(1) <= 0.02 * cap},
                              index=pd.date_range(load.index[0], periods=365)).groupby(lambda d: d.month).mean() * 100
            fig = go.Figure()
            fig.add_bar(x=MESI, y=pm["piena"], name="Giorni in cui si riempie", marker_color=VERDE_CH)
            fig.add_bar(x=MESI, y=pm["vuota"], name="Giorni in cui si svuota", marker_color=BLU)
            fig.update_layout(barmode="group", title="Quanto spesso la batteria si riempie e si svuota")
            st.plotly_chart(style(fig, h=320, ytitle="% dei giorni"), width="stretch")
            st.caption("Piena quasi ogni giorno d'estate: la batteria limita. Mai piena d'inverno: "
                       "il sole non basta a caricarla e capacità in più resterebbe inutilizzata.")
        wk = st.select_slider("Settimana da visualizzare", options=list(range(1, 53)), value=3,
                              format_func=lambda w: (lambda d: f"{d.day} {MESI[d.month - 1]}")(
                                  load.index[0] + pd.Timedelta(weeks=w - 1)))
        s = df.iloc[(wk - 1) * 7 * 96: wk * 7 * 96]
        fig = go.Figure()
        fig.add_scatter(x=s.index, y=s["carico"] * 4, name="Consumo [kW]", line=dict(color=BLU, width=1.5))
        fig.add_scatter(x=s.index, y=s["fv"] * 4, name="Produzione FV [kW]", line=dict(color=OCRA, width=1.5),
                        fill="tozeroy", fillcolor=stile.trasparente(OCRA, 0.15))
        if kwh > 0:
            fig.add_scatter(x=s.index, y=s["soc"] / (kwh * dod) * 100, name="Carica batteria [%]",
                            yaxis="y2", line=dict(color=VERDE, width=2, dash="dot"))
            fig.update_layout(yaxis2=dict(overlaying="y", side="right", range=[0, 105], dtick=25,
                                          title="%", showgrid=False))
        fig.update_xaxes(tickformat="%d/%m", dtick=86400000)
        st.plotly_chart(style(fig, h=360, ytitle="kW"), width="stretch")

    with st.expander("I tuoi consumi"):
        c = st.columns(4)
        c[0].metric("Consumo annuo", f"{num(consumo)} kWh")
        if stima is None:
            c[1].metric("Giorni misurati", f"{rep.giorni_validi} / 365")
            c[2].metric("Picco sul quarto d'ora", f"{num(picco, 1)} kW")
        else:
            c[1].metric("Origine dei dati", "Profilo stimato")
            c[2].metric("Picco sul quarto d'ora", "n.d.", help="Un profilo stimato non mostra i picchi reali.")
        c[3].metric("Produzione FV", f"{num(pv1.sum())} kWh/kW",
                    help=f"PVGIS, anno meteo {yrs[S.adv_meteo]}")
        gaps = parser.missing_ranges(rep.giorni_mancanti)
        if gaps:
            txt = ", ".join(f"{a:%d/%m}–{b:%d/%m}" if a != b else f"{a:%d/%m}" for a, b in gaps)
            st.caption(f"Giorni mancanti nel file, ricostruiti con giorni simili vicini: {txt}.")
        if stima is not None:
            st.caption("Profilo stimato: la potenza del contatore non si può ricavare dai picchi, quindi si usa "
                       "quella che indichi (3 kW se non la conosci).")
        elif p_imp is None:
            st.caption(f"Dai picchi stimiamo una potenza impegnata di almeno {num(p_stimata, 1)} kW.")
        elif picco > p_imp * 1.1:
            st.warning(f"I tuoi consumi arrivano a {num(picco, 1)} kW medi sul quarto d'ora, sopra i "
                       f"{num(p_imp, 1)} kW indicati: verifica in bolletta la potenza impegnata.")
        m = load.groupby(load.index.month).sum()
        fig = go.Figure()
        fig.add_bar(x=MESI, y=m.values, name="Consumo", marker_color=BLU)
        fig.add_scatter(x=MESI, y=pv1.groupby(pv1.index.month).sum().values * kwp,
                        name=f"Produzione FV {num(kwp, 1)} kW", mode="lines+markers", line=dict(color=OCRA, width=3))
        st.plotly_chart(style(fig, h=340, ytitle="kWh/mese"), width="stretch")
        c1, c2 = st.columns(2)
        with c1:
            nd = load.groupby(load.index.month).apply(lambda x: x.index.normalize().nunique())
            prof = load.groupby([load.index.month, load.index.hour]).sum().unstack() / nd.to_numpy()[:, None]
            fig = go.Figure()
            for lbl, months, col in [("Inverno (dic–feb)", [12, 1, 2], STAGIONI["Inverno"]),
                                     ("Mezza stagione", [3, 4, 5, 9, 10, 11], STAGIONI["Primavera"]),
                                     ("Estate (giu–ago)", [6, 7, 8], STAGIONI["Estate"])]:
                fig.add_scatter(x=list(range(24)), y=prof.loc[months].mean().values, name=lbl,
                                line=dict(color=col, width=3))
            fig.update_layout(title="Giornata tipo")
            fig.update_xaxes(title="ora", dtick=3)
            st.plotly_chart(style(fig, h=360, ytitle="kW medi"), width="stretch")
        with c2:
            z = load.to_numpy().reshape(365, 96) * 4
            fig = go.Figure(go.Heatmap(z=z.T, x=pd.date_range(load.index[0], periods=365), y=np.arange(96) / 4,
                                       colorscale=stile.SCALA_FREDDO, colorbar=dict(title="kW")))
            fig.update_layout(title="Tutto l'anno, quarto d'ora per quarto d'ora")
            fig.update_yaxes(title="ora", dtick=3, autorange="reversed")
            fig.update_xaxes(tickvals=pd.date_range(load.index[0], periods=12, freq="MS"), ticktext=MESI)
            st.plotly_chart(style(fig, h=360), width="stretch")

    with st.expander("Ipotesi di calcolo"):
        st.markdown("\n".join("- " + x for x in ipotesi))
        st.markdown("**Non considerati nel calcolo economico**\n" + "\n".join("- " + x.capitalize() for x in non_considerati))
        st.caption(nota_economica)

    with st.expander("Altre opportunità da valutare"):
        st.markdown(
            "- **Comunità energetiche rinnovabili (CER)**: l'energia immessa in rete e consumata da altri "
            "membri nella stessa ora riceve una tariffa incentivante per 20 anni.\n"
            "- **Reddito energetico**: contributo a fondo perduto per famiglie con ISEE basso, quando c'è "
            "un bando aperto.\n"
            "- **Contributi regionali o comunali**: verifica i bandi del tuo territorio.")

# ================================================================ 6. parametri avanzati
with st.expander("Parametri avanzati"):
    st.caption("I valori proposti vengono dal file dei parametri standard. Se li modifichi, in cima al "
               "risultato compare un avviso con il pulsante per ripristinarli.")
    t1, t2, t3, t4, t5 = st.tabs(["Costi e prezzi", "Analisi economica", "Batteria",
                                  "Fotovoltaico e rete", "Scegli tu kW e kWh"])
    with t1:
        c = st.columns(3)
        c[0].number_input("Costo FV [€/kW]", 500.0, 4000.0, step=50.0, key="adv_fv_eur")
        c[1].number_input("Costo batteria [€/kWh]", 100.0, 1500.0, step=25.0, key="adv_batt_eur")
        c[2].number_input("Costo fisso batteria [€]", 0.0, 5000.0, step=100.0, key="adv_batt_fisso")
        c = st.columns(3)
        c[0].number_input("Energia prelevata [€/kWh]", 0.05, 0.80, step=0.01, key="adv_prezzo")
        c[1].number_input("Energia immessa [€/kWh]", 0.0, 0.30, step=0.01, key="adv_immesso")
        c[2].number_input("Manutenzione [€/kW/anno]", 0.0, 100.0, step=5.0, key="adv_manut")
    with t2:
        c = st.columns(3)
        c[0].slider("Tasso di sconto [%]", 0.0, 8.0, step=0.5, key="adv_tasso")
        c[1].slider("Crescita prezzo energia [%/anno]", 0.0, 6.0, step=0.5, key="adv_infl")
        c[2].slider("Orizzonte [anni]", 10, 30, key="adv_orizzonte")
        c = st.columns(3)
        c[0].slider("Degrado moduli [%/anno]", 0.0, 1.0, step=0.1, key="adv_degrado")
        c[1].slider("Vita batteria [anni]", 8, 25, key="adv_vita_batt")
        c[2].slider("Costo sostituzione batteria [% di oggi]", 20, 100, step=5, key="adv_sost")
    with t3:
        c = st.columns(4)
        c[0].slider("Capacità utile [%]", 70, 100, key="adv_dod")
        c[1].slider("Rendimento [%]", 80, 98, key="adv_eta")
        c[2].slider("Potenza / capacità [C]", 0.2, 1.0, step=0.1, key="adv_crate")
        c[3].number_input("Potenza minima [kW]", 0.0, 10.0, step=0.5, key="adv_pmin")
    with t4:
        c = st.columns(3)
        c[0].slider("Perdite di sistema [%]", 5, 25, key="adv_perdite")
        c[1].radio("Anno meteo", ["mediana", "min", "max"], horizontal=True, key="adv_meteo",
                   help=f"Anno con produzione mediana, minima o massima nel "
                        f"{FV['pvgis_anno_inizio']}-{FV['pvgis_anno_fine']}")
        with c[2]:
            st.toggle("Inclinazione esatta", key="adv_incl_on")
            if S.adv_incl_on:
                st.slider("Inclinazione [°]", 0, 60, key="adv_incl")
        st.toggle(f"Limita l'immissione alla potenza del contatore ({num(p_cont * 1.1, 1)} kW disponibili), "
                  "cioè senza adeguamento", key="adv_lim")
    with t5:
        st.toggle("Usa la mia configurazione al posto della proposta", key="adv_libera")
        c = st.columns(2)
        c[0].number_input("Fotovoltaico [kW]", 1.0, 20.0, step=0.5, key="adv_kwp")
        c[1].number_input("Batteria [kWh]", 0.0, 40.0, step=0.5, key="adv_kwh")

footer()
