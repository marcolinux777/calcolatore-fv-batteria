"""Prove di engine/profili.py. Si lanciano con:  python tests/test_profili.py  (oppure pytest)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import profili as P  # noqa: E402

FASCE = P.mappa_fasce()
MESE, TIPO = P._calendario()


def quote(anno):
    s = np.array([anno[FASCE == f].sum() for f in range(3)])
    return s / s.sum()


def test_dati_e_regioni():
    assert len(P.regioni_disponibili()) == 20
    assert P.regione_arera("Piemonte") == "Piemonte"
    assert P.regione_arera("Trentino-Alto Adige/Südtirol") == "Trentino-Alto Adige"
    assert P.regione_arera("Valle d'Aosta/Vallée d'Aoste") == "Valle d'Aosta"
    assert P.regione_arera("Friuli Venezia Giulia") == "Friuli-Venezia Giulia"
    assert P.regione_arera("") is None and P.regione_arera("Francia") is None


def test_consumi_tipici_piemonte():
    t = P.consumo_tipico("Piemonte")
    assert abs(t["3_a_4_5"] - 2799) < 5 and abs(t["1_5_a_3"] - 1622) < 5
    assert P.scegli_classe(1500, "Piemonte") == "1_5_a_3"
    assert P.scegli_classe(2800, "Piemonte") == "3_a_4_5"
    assert P.scegli_classe(4000, "Piemonte") == "4_5_a_6"


def test_quote_fasce_tipiche_coerenti_con_arera():
    # Piemonte, 3-4,5 kW: ARERA (file mensile) F1 30.7 / F2 30.7 / F3 38.6 %
    q = P.quote_fasce_tipiche("Piemonte", "3_a_4_5")
    assert abs(q[0] - 0.307) < 0.015 and abs(q[1] - 0.307) < 0.02 and abs(q[2] - 0.386) < 0.02, q


def test_consumo_annuo_totale_e_forma():
    p = P.da_consumo_annuo(2800, regione="Piemonte", rugosita=0)
    assert abs(p.totale_kwh - 2800) < 1e-6 and p.anno.shape == (365, 96)
    assert (p.anno > 0).all()
    # picco serale nei giorni feriali di gennaio, minimo di notte
    g = p.anno[(MESE == 0) & (TIPO == 0)].mean(axis=0)
    assert 18 <= g.argmax() / 4 < 22 and g[8:20].mean() < g.max()
    assert g.argmin() / 4 < 6
    # inverno piu' alto dell'estate
    assert p.anno[MESE == 0].sum() > p.anno[MESE == 5].sum()


def test_presenza_e_pompa_di_calore():
    base = P.da_consumo_annuo(2800, regione="Piemonte", rugosita=0).anno
    sempre = P.da_consumo_annuo(2800, regione="Piemonte", presenza="sempre", rugosita=0).anno
    mai = P.da_consumo_annuo(2800, regione="Piemonte", presenza="quasi mai", rugosita=0).anno
    ore = slice(40, 68)  # 10:00-17:00
    fer = TIPO == 0
    assert sempre[fer][:, ore].sum() > base[fer][:, ore].sum() > mai[fer][:, ore].sum()
    pdc = P.da_consumo_annuo(2800, regione="Piemonte", pompa_calore=True, rugosita=0).anno
    inv = lambda a: a[np.isin(MESE, [11, 0, 1])].sum() / a.sum()  # noqa: E731
    assert inv(pdc) > inv(base) + 0.03


def test_fasce_annuali_esatte():
    p = P.da_fasce(1000, 800, 1000, regione="Piemonte")
    for f, v in enumerate((1000, 800, 1000)):
        assert abs(p.anno[FASCE == f].sum() - v) < 1e-6
    assert p.metodo == "fasce_annuali" and p.residuo_max_pct < 1e-6


def test_fasce_con_mesi_e_matrice():
    mensili = [330, 300, 260, 220, 200, 210, 240, 240, 210, 230, 280, 340]
    p = P.da_fasce(1000, 800, 1000, mensili=mensili, regione="Lombardia")
    att = np.array(mensili) * 2800 / sum(mensili)
    for m in range(12):
        assert abs(p.anno[MESE == m].sum() - att[m]) < 0.01
    for f, v in enumerate((1000, 800, 1000)):
        assert abs(p.anno[FASCE == f].sum() - v) < 0.01
    rng = np.random.default_rng(1)
    mat = rng.uniform(40, 120, size=(12, 3))
    q = P.da_fasce(0, 0, 0, matrice=mat.tolist(), regione="Veneto")
    for m in range(12):
        for f in range(3):
            assert abs(q.anno[(MESE == m)[:, None] & (FASCE == f)].sum() - mat[m, f]) < 1e-6


def test_serie_e_avvisi():
    p = P.da_consumo_annuo(2700)           # senza regione: media italiana
    s = p.serie
    assert len(s) == 35040 and abs(s.sum() - 2700) < 1e-6
    assert str(s.index[0]) == f"{P.ANNO_RIF}-01-01 00:00:00" and not p.picchi_affidabili and p.avvisi
    assert any("F1" in a for a in P.da_fasce(1800, 400, 500, regione="Piemonte").avvisi)
    for bad in (lambda: P.da_consumo_annuo(0), lambda: P.da_consumo_annuo(1000, presenza="boh"),
                lambda: P.da_fasce(-1, 1, 1)):
        try:
            bad()
        except ValueError:
            continue
        raise AssertionError("atteso ValueError")


def test_rugosita_riduce_autoconsumo():
    t = (np.arange(96) + 0.5) / 4
    g = np.clip(np.sin(np.pi * (t - 6) / 13), 0, None)
    stag = 0.35 + 0.65 * np.sin(np.pi * (np.arange(365) - 80) / 365) ** 2
    FV = stag[:, None] * g[None, :]
    FV *= 3 * 1250 / FV.sum()
    ac = [np.minimum(FV, P.da_consumo_annuo(2700, regione="Piemonte", rugosita=r).anno).sum() / FV.sum()
          for r in (0.0, 0.5, 0.8)]
    assert ac[0] > ac[1] > ac[2], ac
    return ac


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            r = f()
            print("ok ", nome, "" if r is None else [round(100 * x, 1) for x in r])
    q = P.quote_fasce_tipiche("Piemonte", "3_a_4_5")
    print("quote F1/F2/F3 Piemonte 3-4,5 kW:", q.round(3))
    print("consumi tipici Piemonte:", {k: round(v) for k, v in P.consumo_tipico("Piemonte").items()})
