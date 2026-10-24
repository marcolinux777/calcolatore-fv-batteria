# Verifica dimensionamento FV + accumulo (fase a, uso locale)

Aggiornare un ambiente esistente dopo nuove dipendenze:
    conda env update -f environment.yml

Avvio:
    conda env create -f environment.yml      (solo la prima volta)
    conda activate accumulo-fv
    streamlit run app.py

Struttura:
- parametri.toml     costi, prezzi, incentivi, ipotesi finanziarie, località: DA AGGIORNARE
                     periodicamente; l'app lo rilegge a ogni modifica, senza riavvio
- engine/parser.py   lettura CSV quartorario Portale Consumi ARERA -> anno tipo 365 x 96
- engine/pv.py       produzione FV da PVGIS seriescalc, 15 min, ora civile
- engine/sim.py      simulazione batteria, scansione kWp x kWh, ginocchio
- engine/finanza.py  flussi di cassa attualizzati, incentivi a rate, scelta per obiettivo
- engine/giudizio.py giudizio qualitativo sul preventivo, stima potenza contatore
- engine/report.py   esportazione PDF (fpdf2 + grafici matplotlib con climaction_palette)
- climaction_palette.py  palette climaction per matplotlib (usata nei grafici del PDF)
- assets/            logo_climaction.png (percorso in parametri.toml, [app] logo)
- engine/config.py   lettura e controllo di parametri.toml
- stile.py           palette climaction (da climaction_palette.py v1.1): template Plotly, CSS, colori
- app.py             interfaccia Streamlit (pagina unica, parametri avanzati in fondo)

Perimetro: solo abitazioni private (persone fisiche, utenze domestiche).

Il CSV caricato resta in memoria. In data/pvgis_cache/ si salvano solo le serie
PVGIS (dati pubblici). La cartella data/ e i file .csv sono esclusi da git.

Limite: il contatore misura solo i prelievi. Chi ha gia' un impianto FV vede
il carico al netto dell'autoconsumo e il dimensionamento risulta sottostimato.
