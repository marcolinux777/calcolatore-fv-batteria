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
- engine/profili.py  profilo di consumo STIMATO (da fasce F1/F2/F3 della bolletta o dal solo consumo annuo)
                     per chi non ha il file; forma dai dati ARERA 2025 per regione
- engine/dati/       forme_arera_2025.json: aggregati ARERA "Monitoraggio retail" (nessun dato personale)
- scripts/           prepara_forme_arera.py rigenera il JSON da Dati_regione_<anno>.zip (serve openpyxl)
- tests/             test_profili.py, test_app.py (python tests/test_<nome>.py)
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

Modalita' di ingresso dei consumi: file del Portale Consumi (preciso), fasce della bolletta, solo
consumo annuo (profili stimati: i picchi reali non si vedono, la potenza del contatore non si
deduce da li' e viene chiesta o assunta pari a 3 kW). Per ora non si raccolgono curve degli utenti.

Aggiornare le forme ARERA con un nuovo anno:
    scaricare Dati_regione_<anno>.zip da arera.it (Dati e statistiche > Analisi dei consumi dei clienti domestici),
    metterlo in data/ e lanciare:  python scripts/prepara_forme_arera.py data/Dati_regione_<anno>.zip <anno>
    poi aggiornare DATI_ARERA in engine/profili.py.
