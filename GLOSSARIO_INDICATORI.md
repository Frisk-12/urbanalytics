# Glossario degli indicatori — Milano Quartieri

Riferimento tecnico per tutti gli indicatori presenti nella dashboard.
Ogni voce riporta: definizione, formula di calcolo, fonti dati e anni di copertura.

---

## Unità geografica

| | |
|---|---|
| **NIL** | Nucleo di Identità Locale — 88 quartieri ufficiali del PGT 2030 di Milano |
| **Fonte geometrie** | ArcGIS REST API del Geoportale del Comune di Milano |
| **Soglia di significatività** | Un NIL è considerato "significativo" se conta almeno 30 attività commerciali (POI). Sotto questa soglia gli indicatori derivati non sono calcolati o sono segnalati come inaffidabili |

---

## 1. Indicatori di prezzo immobiliare

### Prezzo medio (EUR/mq)
- **Definizione**: prezzo medio di compravendita per metro quadro di abitazioni civili in stato normale (stato prevalente)
- **Calcolo**: media ponderata per area dei valori OMI delle zone che intersecano il NIL. Per ogni NIL si identificano le zone OMI sovrapposte, si calcola la superficie di intersezione e si usa come peso per la media dei prezzi (spatial join area-weighted)
- **Fonte**: OMI — Osservatorio del Mercato Immobiliare, Agenzia delle Entrate
- **Dato**: quotazioni semestrali, filtrate per tipologia "Abitazioni civili", stato "NORMALE", stato prevalente = "P"
- **Copertura**: dal 2° semestre 2004 al 2° semestre 2024
- **Aggiornamento**: semestrale
- **Zone OMI**: 41 zone per Milano (fasce B, C, D, E, R), mappate sui 88 NIL tramite intersezione geometrica

### Range prezzo (EUR/mq)
- **Definizione**: intervallo minimo-massimo delle quotazioni OMI
- **Calcolo**: media ponderata per area di `Compr_min` e `Compr_max`
- **Fonte**: OMI, stessi filtri del prezzo medio

### Trend prezzi 5 anni (%)
- **Definizione**: variazione percentuale del prezzo medio tra il semestre più recente e quello di 5 anni prima
- **Calcolo**: `(prezzo_2024H2 / prezzo_2019H2) - 1`
- **Fonte**: OMI, serie storica

### Trend prezzi 10 anni (%)
- **Definizione**: variazione percentuale del prezzo medio su 10 anni
- **Calcolo**: `(prezzo_2024H2 / prezzo_2014H2) - 1`
- **Fonte**: OMI, serie storica

### Fascia OMI
- **Definizione**: classificazione della zona OMI dominante nel NIL
- **Valori**: B = centrale, C = semicentrale, D = periferica, E = suburbana, R = rurale
- **Calcolo**: fascia della zona OMI con maggiore sovrapposizione areale sul NIL

---

## 2. Indicatori demografici (ISTAT)

Tutti gli indicatori demografici derivano dal Censimento permanente ISTAT 2023, a livello di sezione di censimento, aggregati ai NIL tramite spatial join area-weighted (sezione → griglia 350m → NIL).

**Fonte**: ISTAT — Censimento permanente della popolazione e delle abitazioni 2023
**Copertura**: anno censuario 2023 (dato statico, non serie storica)
**Codice comune ISTAT Milano**: 15146

### Popolazione totale
- **Definizione**: numero di residenti nel NIL
- **Campo ISTAT**: `P1` (popolazione residente)
- **Calcolo**: somma pesata per area delle sezioni censuarie

### % Laureati
- **Definizione**: quota di residenti con titolo di studio terziario (laurea o superiore) sul totale della popolazione con 9+ anni
- **Calcolo**: `edu_tertiary / pop_9plus`
- **Campi ISTAT**: `P47` (laurea e post-laurea) / `P33` (pop. 9 anni e più)

### % Stranieri
- **Definizione**: quota di residenti con cittadinanza straniera
- **Calcolo**: `pop_foreign / pop_tot`
- **Campo ISTAT**: `ST1` / `P1`

### % Giovani (0-19 anni)
- **Definizione**: quota di popolazione in età 0-19
- **Calcolo**: `(pop_0_4 + pop_5_9 + pop_10_14 + pop_15_19) / pop_tot`
- **Campi ISTAT**: `P14 + P15 + P16 + P17` / `P1`

### % Anziani (65+ anni)
- **Definizione**: quota di popolazione con 65 anni e oltre
- **Calcolo**: `(pop_65_69 + pop_70_74 + pop_over74) / pop_tot`
- **Campi ISTAT**: `P29 + P30 + P31` / `P1`

### Indice di vecchiaia
- **Definizione**: rapporto tra anziani (65+) e giovani (0-19). Valori > 1 indicano più anziani che giovani
- **Calcolo**: `pop_old / pop_young`
- **Interpretazione**: Milano ha una mediana di ~1.3; valori sopra 2.5 segnalano quartieri fortemente invecchiati

### % Occupati
- **Definizione**: quota di occupati sulla popolazione in età lavorativa
- **Campi ISTAT**: `P60` / popolazione 15-64

### % Abitazioni vuote
- **Definizione**: quota di abitazioni non occupate sul totale
- **Calcolo**: `housing_empty / housing_total`
- **Campi ISTAT**: `A2 - A3` / `A2` (totale abitazioni - occupate)

### % Famiglie monocomponente
- **Definizione**: quota di nuclei familiari composti da una sola persona
- **Calcolo**: `fam_1p / families`
- **Campi ISTAT**: `PF2` / `PF1`

### Dimensione media familiare
- **Definizione**: numero medio di componenti per famiglia
- **Calcolo**: `pop_tot / families`

---

## 3. Indicatori commerciali (OpenStreetMap)

Basati sull'ultima snapshot disponibile dei POI (Points of Interest) da OpenStreetMap.
**NON** vengono utilizzate serie storiche dei POI in quanto considerate inaffidabili per analisi temporali (la copertura OSM varia nel tempo per ragioni editoriali, non reali).

**Fonte**: OpenStreetMap via Overpass API
**Snapshot utilizzata**: 2° trimestre 2026 (ultima disponibile)
**Copertura**: solo dati cross-sezionali (confronto tra quartieri), nessun trend

### Conteggio attività (poi_count)
- **Definizione**: numero totale di POI commerciali e di servizio mappati nel NIL
- **Calcolo**: conteggio diretto dei POI geolocalizzati entro il perimetro del NIL
- **Categorie incluse**: 14 macro-categorie (negozi base, premium, ristorazione, cultura, lifestyle, servizi essenziali, servizi professionali, istituzioni, consumo, spazio pubblico, servizi urbani, infrastruttura, locali sfitti, altro)

### Densità commerciale (poi_density)
- **Definizione**: numero di attività ogni 1.000 residenti
- **Calcolo**: `(poi_count / pop_tot) × 1000`
- **Fonti**: OSM (POI) + ISTAT (popolazione)
- **Interpretazione**: valori alti (>30) indicano poli attrattori; valori bassi (<10) indicano zone sottoservite

### Residenti per attività
- **Definizione**: quanti residenti ci sono per ogni attività commerciale
- **Calcolo**: `pop_tot / poi_count`
- **Interpretazione**: inverso della densità. Valori bassi (<20) = polo attrattore; valori alti (>80) = zona sottoservita

### % Premium (poi_premium_share)
- **Definizione**: quota di attività classificate come premium sul totale
- **Calcolo**: `conteggio POI premium / poi_count`
- **Classificazione**: la categoria "premium" include boutique, gallerie d'arte, ristoranti fine dining, hotel di lusso, negozi di design, enoteche, gioiellerie — secondo un mapping manuale dei tag OSM

### Entropia commerciale (poi_entropy)
- **Definizione**: indice di diversità del mix funzionale, basato sull'entropia di Shannon normalizzata
- **Calcolo**: `H = -Σ(p_i × ln(p_i)) / ln(N)` dove `p_i` è la quota della categoria i-esima e `N` il numero di categorie presenti
- **Range**: 0 (monocultura) → 1 (perfetta diversificazione)
- **Interpretazione**: valori > 0.7 indicano un mix funzionale ricco e resiliente

### Quote per categoria (poi_share_*)
- **Definizione**: quota percentuale di ogni macro-categoria sul totale POI del NIL
- **Calcolo**: `conteggio POI della categoria / poi_count`
- **Categorie**: retail_base, retail_premium, hospitality_tourism, culture, lifestyle, essential_services, professional_services, civic_institutional, consumption, public_realm, urban_amenities, urban_infrastructure, vacancies, other

---

## 4. Indicatori satellitari

**Fonte**: Google Earth Engine — Sentinel-2 e dataset derivati
**Copertura**: media trimestrale, aggregata a livello NIL

### NDVI medio
- **Definizione**: Normalized Difference Vegetation Index — indice di copertura vegetale
- **Calcolo**: `(NIR - RED) / (NIR + RED)` da bande Sentinel-2, media dei pixel nel NIL
- **Range**: -1 → 1 (valori > 0.3 indicano vegetazione significativa)
- **Fonte**: Sentinel-2 via Google Earth Engine
- **Nota**: nel quality_score viene applicato un cap a 0.30 per rendimenti decrescenti

### Indice di costruito (builtup_mean)
- **Definizione**: frazione media di superficie costruita nel NIL
- **Calcolo**: media dei pixel di indice di costruito (built-up index) entro il perimetro del NIL
- **Range**: 0 → 1 (0 = nessun costruito, 1 = completamente edificato)
- **Fonte**: dataset derivato Sentinel-2 via Google Earth Engine
- **Nota**: nel quality_score viene applicato un floor a 0.15 per attenuare la penalità nei quartieri con costruito moderato
- **Fallback**: se il trimestre più recente non ha dati satellitari, il sistema cerca automaticamente il trimestre precedente più recente disponibile (stessa logica per NDVI)

---

## 4b. Indicatori infrastrutturali (Comune di Milano)

Dati open data del Comune di Milano, aggregati a livello NIL tramite spatial join (punti dentro poligoni) o ID_NIL diretto dove disponibile.

**Fonte**: Portale Open Data del Comune di Milano
**Copertura**: dataset statici (ultimo aggiornamento disponibile)

### Fermate TPL (tpl_stops)
- **Definizione**: numero di fermate del trasporto pubblico locale (autobus e tram) nel NIL
- **Calcolo**: point-in-polygon delle 4.690 fermate nei confini NIL
- **Fonte**: Comune di Milano — dataset `tpl_fermate_shp`

### Linee TPL (tpl_lines)
- **Definizione**: numero di linee distinte di autobus/tram che servono il NIL
- **Calcolo**: conteggio delle linee uniche associate alle fermate nel NIL
- **Interpretazione**: misura la **connettività** (quante direzioni diverse puoi raggiungere), non la capillarità

### Fermate Metro (metro_stops)
- **Definizione**: numero di stazioni della metropolitana nel NIL
- **Calcolo**: point-in-polygon delle 130 fermate metro nei confini NIL
- **Fonte**: Comune di Milano — dataset `tpl_metrofermate_shp`

### Linee Metro (metro_lines)
- **Definizione**: numero di linee metro distinte che servono il NIL (0-4)
- **Interpretazione**: avere 2+ linee metro = snodo di interscambio

### Connettività trasporto (connectivity)
- **Definizione**: indice composito di accessibilità al trasporto pubblico
- **Calcolo**: `metro_lines × 5 + tpl_lines`
- **Interpretazione**: il peso 5× per le linee metro riflette l'impatto maggiore del servizio metropolitano rispetto al bus. Duomo (42) è il NIL più connesso, seguito da Buenos Aires (38) e Magenta/Brera (32)
- **Nota**: usato nel quality_score al posto del transit_per_1000 (per-capita), che distorceva a favore dei quartieri poco popolati

### Impianti sportivi (sport_facilities)
- **Definizione**: numero di impianti sportivi pubblici e privati nel NIL
- **Calcolo**: aggregazione per ID_NIL (campo già presente nel dataset originale)
- **Fonte**: Comune di Milano — dataset `ds34_impianti_sportivi`
- **Copertura**: 1.041 impianti mappati su 73 NIL
- **Nota**: nel quality_score si usa `log(1 + count)` per attenuare gli outlier

### Parchi (park_area_mq, park_count)
- **Definizione**: superficie totale e conteggio dei parchi e giardini pubblici nel NIL
- **Calcolo**: assegnazione per centroide del poligono parco, somma delle aree in mq
- **Fonte**: Comune di Milano — dataset `parchi`
- **Copertura**: 1.065 aree verdi per un totale di 7.7 km², mappate su 53 NIL
- **Nota**: nel quality_score si usa `park_area_mq / pop_tot` con cap a 10 mq/ab per rendimenti decrescenti. Complementare all'NDVI: i parchi sono infrastrutture puntuali, l'NDVI misura il verde diffuso

### Biblioteche e archivi (libraries)
- **Definizione**: numero di biblioteche, archivi e strutture culturali pubbliche nel NIL
- **Calcolo**: point-in-polygon delle 232 strutture nei confini NIL
- **Fonte**: Comune di Milano — dataset `ds41_bibliotechearchivi2007_00_00`
- **Copertura**: 232 strutture mappate su 54 NIL
- **Nota**: non incluso nel quality_score (distribuzione troppo disomogenea, include archivi speciali non legati alla qualità di quartiere)

---

## 5. Indici compositi

### Qualità della vita (quality_score) — v4c

- **Definizione**: indice composito che misura la qualità complessiva della vita nel quartiere, basato su cosa offre il quartiere (servizi, trasporti, infrastrutture) piuttosto che su chi ci abita
- **Scala**: 0-100 (normalizzazione min-max tra i NIL eleggibili)
- **Soglia di eleggibilità**: il NIL deve avere almeno **30 attività** e **2.000 residenti**. I NIL troppo piccoli (es. Parco Sempione, Roserio, Assiano) non ricevono un punteggio perché le metriche risultano distorte. Attualmente: 70 NIL eleggibili, 18 esclusi
- **Struttura a 4 macro-componenti**:

#### OFFERTA COMMERCIALE (42%) — mix e densità servizi privati
| Componente | Peso | Descrizione |
|---|---|---|
| Entropia commerciale | 20% | Diversità del mix funzionale (Shannon normalizzato). Un quartiere con tanti tipi di servizi diversi è più vivibile |
| Servizi essenziali per 1.000 ab. | 12% | `poi_density × poi_share_essential_services`. Misura quanti servizi essenziali ci sono **pro-capite**, non quale quota rappresentano |
| Curva di densità (sigmoid) | 10% | Formula: `1 - exp(-d/20)`. Plateau sopra ~60 POI/1000ab. La sigmoid lenta discrimina meglio tra quartieri a bassa densità (periferici) e ad alta densità (centrali) |

#### ACCESSIBILITÀ (17%) — connettività trasporto pubblico
| Componente | Peso | Descrizione |
|---|---|---|
| Connettività trasporto | 17% | `metro_lines × 2 + tpl_lines`. Conta le **linee distinte** che servono il quartiere, non le fermate. Metro pesata solo 2× (non 5×): a Milano il tram è un mezzo primario, con linee ad alta frequenza (1, 3, 9, 15, 19) che valgono quasi quanto una metro. Non usa metriche per-capita (evita il bias dei quartieri poco popolati) |

#### SERVIZI PUBBLICI (6%) — infrastrutture ufficiali
| Componente | Peso | Descrizione |
|---|---|---|
| Impianti sportivi | 3% | `log(1 + count)` degli impianti sportivi nel NIL. Il logaritmo attenua gli outlier |
| Parchi | 3% | Metri quadri di parco per residente, con cap a 10 mq/ab per rendimenti decrescenti |

#### AMBIENTE (8%) — verde satellitare e costruito
| Componente | Peso | Descrizione |
|---|---|---|
| NDVI (capped a 0.30) | +5% | Verde satellitare, complementare ai dati parchi. Cap per rendimenti decrescenti |
| Builtup (floor a 0.15) | -2% | Penalità cemento attenuata |
| Vacancy (floor a 15%) | -1% | Solo lo sfitto **anomalo** sopra il 15% viene penalizzato. Sotto il 15% è fisiologico in una città. In centro lo sfitto elevato riflette seconde case, investimenti e Airbnb, non degrado |

#### STRUTTURA (-2%) — solo invecchiamento
| Componente | Peso | Descrizione |
|---|---|---|
| Indice di vecchiaia | -2% | Penalità per invecchiamento estremo |

> **Nota**: `pct_employed` è stato rimosso in v4c. In centro l'occupazione bassa riflette la composizione demografica (pensionati benestanti, studenti fuorisede, lavoratori autonomi) e non la qualità del quartiere. Questo indicatore favoriva sistematicamente i quartieri residenziali middle-class.

- **Calcolo finale**: somma pesata di tutti i componenti → normalizzazione min-max a 0-100
- **Correlazione con il prezzo**: r ≈ 0.62 — positiva e significativa. Non troppo alta (non è un proxy del prezzo) e non troppo bassa (cattura qualcosa di reale). Top-5: Duomo, Magenta, Brera, Guastalla, Isola
- **Scelte metodologiche chiave**:
  - **5 fonti dati indipendenti**: OSM (commercio), Comune di Milano (trasporti, sport, parchi), ISTAT (demografia), Sentinel-2 (verde/costruito), OMI (solo per il value_score)
  - Connettività misurata in **linee distinte**, non fermate per-capita
  - Metro × 2 (non × 5): il tram milanese è un mezzo primario
  - Density sigmoid lenta (`d/20`): differenzia meglio quartieri densi vs sparsi
  - Vacancy con floor al 15%: sfitto fisiologico non penalizzato
  - Servizi essenziali **per capita** anziché **quota**: evita di premiare quartieri monotoni
  - Nessun proxy di reddito (laureati, prezzi) per evitare circolarità con il value_score
  - Min-max preserva le distanze reali
- **Fonti combinate**: OSM + ISTAT 2023 + Sentinel-2 + Comune di Milano (TPL, metro, impianti sportivi, parchi)

### Rapporto qualità-prezzo (value_score)
- **Definizione**: misura quanto la qualità della vita è superiore (o inferiore) a quanto ci si aspetterebbe dalla fascia di prezzo
- **Scala**: 0-100
- **Calcolo**: `quality_score - (price_percentile × 100)`, poi normalizzato min-max a 0-100
- **Interpretazione**: un NIL con qualità alta e prezzo basso avrà un value_score alto (quartiere sottovalutato); un NIL costoso ma con servizi scarsi avrà un value_score basso (sopravvalutato)
- **Fonti combinate**: quality_score + OMI

### Attrattività investimento — IAI (iai_score)
- **Definizione**: indice composito di attrattività per investimenti immobiliari e commerciali
- **Scala**: 0-100 (rango percentile)
- **Componenti** (somma pesata dei ranghi percentile):
  - Momentum prezzi (trend OMI 5 anni): peso 25%
  - Vitalità demografica (composito giovani + occupati + laureati): peso 20%
  - Gap di servizi (residenti per attività): peso 20%
  - Accessibilità economica (prezzo invertito): peso 15%
  - Verde e vivibilità (NDVI): peso 10%
  - Basso sfitto abitativo: peso 10%
- **Calcolo**: somma pesata normalizzata → rango percentile → scala 0-100
- **Fonti combinate**: OMI + ISTAT 2023 + OSM + Sentinel-2
- **Soglia**: calcolato solo per NIL con almeno 30 attività

### Opportunity Score per categoria (opp_*)
- **Definizione**: punteggio che indica quanto una specifica categoria commerciale rappresenta un'opportunità nel quartiere, basato sul rapporto tra domanda potenziale e offerta attuale
- **Scala**: 0-100 (rango percentile)
- **Calcolo**: `domanda × 0.6 + (1 - offerta) × 0.4`, dove:
  - *domanda*: composito pesato di driver demografici specifici per categoria (rango percentile)
  - *offerta*: rango percentile della quota attuale della categoria (invertito: meno ce n'è, più è un'opportunità)
- **Soglia**: calcolato solo per NIL con popolazione minima (varia per categoria: 3.000-8.000 residenti) e almeno 30 attività

#### Driver di domanda per categoria:

| Categoria | Driver | Pesi |
|---|---|---|
| Ristorazione e turismo | Popolazione, laureati, giovani, densità commerciale | 30%, 25%, 20%, 25% |
| Lifestyle e benessere | Laureati, giovani, prezzo/mq, occupati | 35%, 25%, 20%, 20% |
| Commercio premium | Prezzo/mq, laureati, densità, occupati | 40%, 30%, 15%, 15% |
| Servizi essenziali | Popolazione, anziani, residenti/attività, stranieri | 30%, 30%, 20%, 20% |
| Negozi di vicinato | Popolazione, residenti/attività, stranieri, anziani | 40%, 30%, 15%, 15% |

### Bacino d'utenza effettivo (catchment_effective)
- **Definizione**: stima del numero di persone che effettivamente frequentano il quartiere, considerando sia i residenti che l'attrattività commerciale
- **Calcolo**: `popolazione × moltiplicatore`, dove il moltiplicatore = `1 + (rango_percentile_densità_commerciale × 0.5)`
- **Range moltiplicatore**: 1.0 (periferia residenziale) → 1.5 (polo attrattore)
- **Fonti**: ISTAT (residenti) + OSM (densità commerciale)

---

## 6. Tipologie di quartiere (identità)

Classificazione qualitativa assegnata automaticamente in base a soglie su indicatori multipli. Ogni NIL riceve una tipologia primaria (mutualmente esclusiva) e zero o più tag secondari.

### Tipologie primarie

| Tipologia | Condizione |
|---|---|
| Lusso | Prezzo > 7.000 €/mq **e** premium > 25% |
| Borghese colto | Prezzo > 5.500 €/mq **e** laureati > 35% |
| Hub commerciale | Attività > 400 **e** densità > 30 per 1.000 ab. |
| Multiculturale | Stranieri > 30% **e** attività > 50 |
| Verde residenziale | NDVI > 0.35 **e** popolazione > 5.000 |
| Storico consolidato | Indice vecchiaia > 2.5 **e** popolazione > 5.000 |
| Giovane e dinamico | Giovani > 18% **e** monocomponente > 55% |
| Quartiere popolare attivo | Popolazione > 20.000 **e** attività > 100 |
| Residenziale | Popolazione > 10.000 |
| Periferico | Popolazione < 3.000 **e** attività < 30 |
| Misto | Nessuna delle precedenti |

### Tag secondari

| Tag | Condizione |
|---|---|
| buon rapporto qualità-prezzo | value_score > 70 **e** attività ≥ 30 |
| sopravvalutato | value_score < 30 **e** prezzo > 5.000 €/mq |
| offerta premium | premium > 30% **e** attività ≥ 30 |
| mix funzionale ricco | entropia > 0.75 **e** attività > 50 |
| alta sfittanza | abitazioni vuote > 20% |
| sottoservito | residenti/attività > 80 **e** popolazione > 5.000 |
| polo attrattore | residenti/attività < 20 **e** attività > 100 |

---

## 7. Segnali di trasformazione

Indicatori binari (presenti/assenti) che segnalano dinamiche in atto. Ogni segnale ha una severità (alta/media) e la fonte è sempre esplicitata.

| Segnale | Condizione | Fonte |
|---|---|---|
| Prezzi in forte crescita | Trend 5 anni > mediana città + 10 punti percentuali | OMI |
| Prezzi sotto la media | Trend 5 anni < mediana città - 5 punti percentuali | OMI |
| Segnale di gentrificazione | Trend 5 anni > 20% **e** laureati > 25% **e** stranieri > 15% **e** fascia D o E | OMI + ISTAT |
| Polo giovani e servizi | Giovani > 17% **e** residenti/attività < 40 **e** popolazione > 10.000 | ISTAT + OSM |
| Rischio invecchiamento | Indice vecchiaia > 3 **e** residenti/attività > 60 | ISTAT + OSM |
| Quartiere sottovalutato | value_score > 75 **e** attività ≥ 30 | Composito |
| Carenza di categoria | Quota categoria < 50% della mediana città **e** attività > 50 | OSM |

---

## Riepilogo fonti

| Fonte | Ente | Dato | Copertura temporale | Granularità |
|---|---|---|---|---|
| OMI | Agenzia delle Entrate | Quotazioni immobiliari | 2004 H2 — 2024 H2 (41 semestri) | 41 zone OMI → 88 NIL |
| Censimento permanente | ISTAT | Popolazione, istruzione, abitazioni | 2023 | 7.095 sezioni censuarie → 88 NIL |
| OpenStreetMap | Comunità OSM | Attività commerciali (POI) | Snapshot Q2 2026 | Puntuali → 88 NIL |
| Sentinel-2 | ESA via Google Earth Engine | NDVI, indice di costruito | 2016-2026 (trimestrale) | Pixel 10m → griglia 350m → 88 NIL |
| Fermate TPL | Comune di Milano | Fermate autobus e tram | Ultimo aggiornamento | 4.690 punti → 88 NIL |
| Fermate Metro | Comune di Milano | Stazioni metropolitana | Ultimo aggiornamento | 130 punti → 88 NIL |
| Impianti sportivi | Comune di Milano | Centri sportivi e impianti | Ultimo aggiornamento | 1.041 punti → 73 NIL |
| Parchi e giardini | Comune di Milano | Aree verdi pubbliche | Ultimo aggiornamento | 1.065 poligoni → 53 NIL |
| Biblioteche/Archivi | Comune di Milano | Biblioteche e archivi pubblici | 2007+ aggiornamenti | 232 punti → 54 NIL |
| Confini NIL | Comune di Milano | Perimetri 88 quartieri PGT 2030 | Vigente | Poligoni |

---

*Ultimo aggiornamento: aprile 2026*
