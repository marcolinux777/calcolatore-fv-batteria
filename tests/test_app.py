"""Prova l'app Streamlit senza rete: PVGIS e geocodifica sono sostituiti da dati sintetici.
Lancio:  python tests/test_app.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import tomllib  # noqa: F401
except ModuleNotFoundError:  # Python < 3.11 (solo per i test fuori dall'ambiente del progetto)
    import tomli
    sys.modules['tomllib'] = tomli

from streamlit.testing.v1 import AppTest  # noqa: E402

from engine import geocode, pv  # noqa: E402
from engine.parser import REF_YEAR  # noqa: E402


def fake_pv(lat, lon, angle=35, orientamento="Sud", loss=14, y0=2014, y1=2023):
    idx = pd.date_range(f"{REF_YEAR}-01-01", periods=365 * 96, freq="15min")
    t = (np.arange(96) + 0.5) / 4
    g = np.clip(np.sin(np.pi * (t - 5.5) / 14), 0, None)
    stag = 0.30 + 0.70 * np.sin(np.pi * (np.arange(365) - 80) / 365) ** 2
    base = stag[:, None] * g[None, :]
    base = base / base.sum() * 1280
    return {y: pd.Series(base.ravel() * (1 + 0.02 * ((y - y0) % 5 - 2)), index=idx) for y in range(y0, y1 + 1)}


pv.pv_profiles = fake_pv
geocode.cerca = lambda q, n=5: [{"nome": "Novara", "provincia": "Novara", "regione": "Piemonte",
                                  "lat": 45.446, "lon": 8.622}]


def nuova():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.run()
    assert not at.exception, at.exception
    return at


def metrica(at, nome):
    return next(m.value for m in at.metric if m.label == nome)


def controlla(at, stimato=True):
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    testo = " ".join([m.value for m in at.markdown] + [i.value for i in at.info])
    if stimato:
        assert "Profilo di consumo stimato" in testo
    return metrica(at, "Consumi coperti dal sole"), metrica(at, "Rientro")


def prova_file_mancante():
    at = nuova()
    assert any("carica il file" in i.value for i in at.info), [i.value for i in at.info]
    print("ok  modo file, senza file: messaggio di avvio")


def prova_consumo_annuo():
    at = nuova()
    at.radio(key="modo").set_value("Indico solo il consumo annuo").run()
    ris = controlla(at)
    print("ok  consumo annuo 2.700 kWh ->", ris)
    # piu' presenza di giorno = piu' autoconsumo
    nuovo = at.radio(key="modo")
    for r in at.radio:
        if r.label.startswith("Di giorno in casa"):
            r.set_value("sempre")
    at.run()
    ris2 = controlla(at)
    print("ok  presenza 'sempre' ->", ris2)
    assert at.radio(key="modo").value == "Indico solo il consumo annuo" and nuovo is not None
    return ris, ris2


def prova_fasce():
    at = nuova()
    at.radio(key="modo").set_value("Ho le fasce F1/F2/F3 della bolletta").run()
    assert any("Inserisci i kWh" in i.value for i in at.info)
    campi = {n.label: n for n in at.number_input}
    campi["F1 [kWh/anno]"].set_value(860)
    campi["F2 [kWh/anno]"].set_value(860)
    campi["F3 [kWh/anno]"].set_value(1080)
    at.run()
    ris = controlla(at)
    print("ok  fasce 860/860/1080 ->", ris)


if __name__ == "__main__":
    prova_file_mancante()
    prova_consumo_annuo()
    prova_fasce()
    print("TUTTO OK")
