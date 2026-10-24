"""Genera engine/dati/forme_arera_<anno>.json dai dati aperti ARERA "Monitoraggio retail".

Uso (dalla cartella del progetto):
    python scripts/prepara_forme_arera.py data/Dati_regione_2025.zip 2025

Fonte: https://www.arera.it/dati-e-statistiche/dettaglio/analisi-dei-consumi-dei-clienti-domestici
(file "Dati regione <anno>.zip", prelievo medio orario dei clienti domestici trattati orari).

Si usano le righe: Tipo mercato = "Tutti", Residenza = "Residente", classi di potenza
1,5-3 / 3-4,5 / 4,5-6 kW. Per ogni regione, classe, mese e tipo di giorno
(feriale, sabato, domenica+festivi) si conserva il prelievo medio orario [kWh/h].
Convenzione ARERA: "Ora N" = intervallo [N-1, N) in ore. Verificata: le quote F1/F2/F3
ricostruite da questi profili coincidono con quelle del file mensile (scarto < 0,5 punti).
Il file generato e' un aggregato statistico, non contiene dati personali.
"""
import io, json, sys, zipfile
from datetime import date, timedelta
from pathlib import Path

import openpyxl
import numpy as np

CLASSI = {"1_5_a_3": "1.5<potenza_impegnata<=3", "3_a_4_5": "3<potenza_impegnata<=4.5",
          "4_5_a_6": "4.5<potenza_impegnata<=6"}
TIPO = {"Giorno feriale": 0, "Sabato": 1, "Domenica": 2}


def _pasqua(y):
    a = y % 19; b, c = divmod(y, 100); d, e = divmod(b, 4); f = (b + 8) // 25
    g = (b - f + 1) // 3; h = (19 * a + b - d - g + 15) % 30; i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7; m = (a + 11 * h + 22 * l) // 451
    mm, dd = divmod(h + l - 7 * m + 114, 31)
    return date(y, mm, dd + 1)


def giorni_per_tipo(anno):
    fest = {date(anno, m, g) for m, g in [(1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15), (11, 1),
                                          (12, 8), (12, 25), (12, 26)]} | {_pasqua(anno) + timedelta(days=1)}
    n = np.zeros((12, 3))
    d = date(anno, 1, 1)
    while d.year == anno:
        t = 2 if (d in fest or d.weekday() == 6) else (1 if d.weekday() == 5 else 0)
        n[d.month - 1, t] += 1
        d += timedelta(days=1)
    return n


def main(zip_path, anno):
    anno = int(anno)
    out = {"fonte": "ARERA, Monitoraggio retail - prelievo medio orario clienti domestici",
           "url": "https://www.arera.it/dati-e-statistiche/dettaglio/analisi-dei-consumi-dei-clienti-domestici",
           "anno": anno, "unita": "kWh/h per cliente medio",
           "convenzione": "ore[mese 0-11][tipo giorno 0 feriale,1 sabato,2 domenica e festivi][ora 0-23]",
           "regioni": {}}
    ndays = giorni_per_tipo(anno)
    z = zipfile.ZipFile(zip_path)
    for cl in CLASSI:
        nome = next(n for n in z.namelist() if f"regionale{cl} " in n and n.endswith(".xlsx"))
        print("leggo", nome, flush=True)
        wb = openpyxl.load_workbook(io.BytesIO(z.read(nome)), read_only=True, data_only=True)
        for i, r in enumerate(wb.active.iter_rows(values_only=True)):
            if i == 0:
                continue
            am, reg, mer, _, res, giorno, ora, kwh = r[:8]
            if str(mer).strip() != "Tutti" or str(res).strip() != "Residente":
                continue
            s = str(am)
            if len(s) < 7:      # riga annuale ("2025"): non serve
                continue
            m = int(s[5:7]) - 1
            reg = str(reg).strip()
            a = out["regioni"].setdefault(reg, {}).setdefault(cl, np.zeros((12, 3, 24)))
            a[m, TIPO[str(giorno).strip()], int(str(ora)[3:]) - 1] = kwh
    for reg, cls in out["regioni"].items():
        for cl, a in cls.items():
            kwh_anno = float((a.sum(axis=2) * ndays).sum())
            cls[cl] = {"kwh_anno": round(kwh_anno), "ore": np.round(a, 4).tolist()}
    dest = Path(__file__).resolve().parent.parent / "engine" / "dati" / f"forme_arera_{anno}.json"
    dest.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print("scritto", dest, round(dest.stat().st_size / 1024), "kB; regioni:", len(out["regioni"]))


if __name__ == "__main__":
    main(*sys.argv[1:3])
