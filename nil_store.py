"""Data store for Milano Quartieri — Neighborhood Intelligence v2.

Philosophy: fewer metrics, deeper analysis, real statistical validation.
Three lenses:
  1. VALORE   — "Quanto vale vivere qui?" (price vs quality of life)
  2. IDENTITA — "Chi vive qui?" (unique demographic + commercial DNA)
  3. SEGNALI  — "Dove sta andando?" (cross-sectional transformation signals)

OSM POI time-series are DISCARDED as unreliable.
Only the LATEST POI snapshot is used for cross-sectional analysis.
House prices from OMI (Agenzia delle Entrate) are area-weighted to NIL.
"""

from __future__ import annotations

import json
import math
import pathlib
import numpy as np
import pandas as pd
from scipy import stats as sp_stats

BASE = pathlib.Path(__file__).resolve().parent
WEBAPP = pathlib.Path(__file__).resolve().parent

# --- Category labels & colors ---
CAT_LABELS = {
    "retail_base": "Negozi di vicinato",
    "retail_premium": "Commercio premium",
    "hospitality_tourism": "Ristorazione e turismo",
    "culture": "Cultura e intrattenimento",
    "lifestyle": "Lifestyle e benessere",
    "essential_services": "Servizi essenziali",
    "professional_services": "Servizi professionali",
    "civic_institutional": "Istituzioni",
    "consumption": "Consumo",
    "public_realm": "Spazio pubblico",
    "urban_amenities": "Servizi urbani",
    "urban_infrastructure": "Infrastruttura",
    "vacancies": "Locali sfitti",
    "other": "Altro",
}

# Minimum POI count for a metric to be statistically meaningful
MIN_POI_SIGNIFICANT = 30


def _safe(v):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return round(float(v), 4)


def _pct(v):
    if v is None:
        return None
    return round(v * 100, 1)


def _fmt_eur(v):
    """Format euros."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return int(round(v))


class NilStore:
    def __init__(self):
        # --- Load data ---
        self.panel = pd.read_parquet(BASE / "data" / "nil" / "nil_panel.parquet")
        self.census = pd.read_parquet(BASE / "data" / "nil" / "nil_census.parquet")
        self.prices = pd.read_parquet(BASE / "data" / "nil" / "nil_price_summary.parquet")
        self.price_ts = pd.read_parquet(BASE / "data" / "nil" / "nil_prices.parquet")

        with open(BASE / "data" / "geojson" / "nil_milano.geojson") as f:
            gj = json.load(f)
        self.nil_geom = {
            feat["properties"]["ID_NIL"]: feat["geometry"]
            for feat in gj["features"]
        }
        self.nil_names = {
            feat["properties"]["ID_NIL"]: feat["properties"]["NIL"]
            for feat in gj["features"]
        }

        # Index on nil_id
        self.census.set_index("nil_id", inplace=True)
        self.prices.set_index("nil_id", inplace=True)

        # Latest quarter only (we don't trust time series)
        self.quarters = sorted(self.panel["year_quarter"].dropna().unique().tolist())
        latest_q = self.quarters[-1]
        self.latest = self.panel[self.panel["year_quarter"] == latest_q].set_index("nil_id").copy()

        # Satellite data may lag — fill from most recent available quarter
        sat_cols = ["ndvi_mean", "builtup_mean"]
        if self.latest[sat_cols].isna().all().all():
            for q in reversed(self.quarters[:-1]):
                fallback = self.panel[self.panel["year_quarter"] == q].set_index("nil_id")
                if fallback[sat_cols].notna().any().any():
                    for c in sat_cols:
                        self.latest[c] = fallback[c]
                    print(f"[NilStore] Satellite data from {q} (latest {latest_q} empty)")
                    break

        # --- Precompute everything ---
        self._build_master()  # unified analysis dataframe
        self._compute_z_scores()
        self._compute_value_score()
        self._compute_identity()
        self._compute_signals()
        self._compute_strategic_scores()
        self._compute_city_summary()

        print(f"[NilStore v2] {len(self.nil_names)} NIL | prices for {len(self.prices)} | latest: {latest_q}")

    # ------------------------------------------------------------------
    # Master DataFrame: merge all sources
    # ------------------------------------------------------------------

    def _build_master(self):
        """Create unified DataFrame with POI + Census + Prices."""
        m = pd.DataFrame(index=list(self.nil_names.keys()))
        m.index.name = "nil_id"
        m["name"] = pd.Series(self.nil_names)

        # POI (latest snapshot only)
        poi_cols = [
            "poi_count", "poi_premium_share", "poi_entropy", "poi_hhi",
            "poi_lq", "poi_turnover", "poi_persistence",
        ]
        for c in poi_cols:
            if c in self.latest.columns:
                m[c] = self.latest[c]

        # Category shares
        share_cols = [c for c in self.latest.columns if c.startswith("poi_share_")]
        for c in share_cols:
            m[c] = self.latest[c]

        m["poi_dominant"] = self.latest.get("poi_dominant")

        # Census
        census_cols = [
            "pop_tot", "pop_young", "pop_old", "pop_working", "pop_foreign",
            "families", "housing_total", "housing_empty",
            "pct_foreign", "pct_old", "pct_young", "pct_employed",
            "pct_tertiary", "pct_housing_empty", "pct_single_hh",
            "avg_family_size", "aging_index",
        ]
        for c in census_cols:
            if c in self.census.columns:
                m[c] = self.census[c]

        # Prices
        price_cols = [
            "price_sqm", "price_min", "price_max",
            "price_change_5y", "price_change_10y", "fascia",
        ]
        for c in price_cols:
            if c in self.prices.columns:
                m[c] = self.prices[c]

        # Derived: density
        m["poi_density"] = np.where(m["pop_tot"] > 0, m["poi_count"] / m["pop_tot"] * 1000, np.nan)
        m["residents_per_poi"] = np.where(m["poi_count"] > 0, m["pop_tot"] / m["poi_count"], np.nan)

        # Satellite (latest)
        for c in ["ndvi_mean", "builtup_mean"]:
            if c in self.latest.columns:
                m[c] = self.latest[c]

        # Infrastructure (Comune di Milano open data)
        infra_path = BASE / "data" / "nil" / "nil_infrastructure.parquet"
        if infra_path.exists():
            infra = pd.read_parquet(infra_path).set_index("nil_id")
            for c in infra.columns:
                m[c] = infra[c]

            # Derived: per-capita infrastructure metrics
            pop = m["pop_tot"].replace(0, np.nan)
            # Transit: metro weighted 3× (higher impact than bus stop)
            m["transit_per_1000"] = (m["tpl_stops"].fillna(0) + m["metro_stops"].fillna(0) * 3) / pop * 1000
            m["has_metro"] = (m["metro_stops"].fillna(0) > 0).astype(int)
            m["sport_per_1000"] = m["sport_facilities"].fillna(0) / pop * 1000
            m["libraries_per_10000"] = m["libraries"].fillna(0) / pop * 10000
            m["park_mq_per_capita"] = m["park_area_mq"].fillna(0) / pop

        # Flag: significant (enough POI for statistics)
        m["is_significant"] = m["poi_count"] >= MIN_POI_SIGNIFICANT

        self.master = m.copy()

    # ------------------------------------------------------------------
    # Z-scores & Percentile ranks
    # ------------------------------------------------------------------

    def _compute_z_scores(self):
        """Standardize key metrics to z-scores and percentile ranks."""
        m = self.master
        sig = m[m["is_significant"]].copy()

        metrics = [
            "poi_count", "poi_density", "poi_premium_share", "poi_entropy",
            "price_sqm", "price_change_5y", "pct_foreign", "pct_tertiary",
            "pct_old", "pct_young", "pct_housing_empty", "aging_index",
            "poi_turnover", "residents_per_poi", "ndvi_mean", "pct_employed",
            "transit_per_1000", "sport_per_1000", "libraries_per_10000",
            "park_mq_per_capita",
        ]

        self.z_scores = {}
        self.percentiles = {}

        for metric in metrics:
            vals = sig[metric].dropna()
            if len(vals) < 10:
                continue

            mu, sigma = vals.mean(), vals.std()
            if sigma == 0:
                continue

            # Z-score for ALL nil (using significant-only distribution)
            z = (m[metric] - mu) / sigma
            self.master[f"z_{metric}"] = z

            # Percentile rank
            pct = m[metric].rank(pct=True)
            self.master[f"pctl_{metric}"] = pct

            self.z_scores[metric] = {"mean": mu, "std": sigma, "n": len(vals)}
            self.percentiles[metric] = True

    # ------------------------------------------------------------------
    # LENS 1: VALUE SCORE — "Quanto vale vivere qui?"
    # ------------------------------------------------------------------

    def _compute_value_score(self):
        """
        Value = quality of neighborhood life per EUR/sqm spent.

        Quality score (v4c) — arricchito con dati Comune di Milano:
          Threshold: poi_count >= 30 AND pop_tot >= 2000
          OFFERTA COMMERCIALE (42%) — mix e densità servizi privati
            poi_entropy:              20%  diversità mix funzionale
            essential_per_1000:       12%  servizi essenziali per capita
            density_curve (sigmoid):  10%  1-exp(-d/20), plateau sopra ~60 POI/1000ab
          ACCESSIBILITÀ (17%) — connettività trasporto pubblico
            connectivity:             17%  metro_lines×2 + tpl_lines
          SERVIZI PUBBLICI (6%) — infrastrutture ufficiali Comune
            sport_facilities (log):    3%  log(1+count)
            park_area (mq, capped):    3%  mq di parco per residente
          AMBIENTE (8%) — verde e costruito
            ndvi_mean (capped .30):    5%  verde
            builtup (floored .15):    -2%  penalità cemento
            vacancy (floor 15%):      -1%  solo vacancy anomalo (>15%)
          STRUTTURA (-2%) — solo invecchiamento
            aging_index:              -2%  penalità invecchiamento

          Note v4c:
            - density sigmoid rallentata (d/20): discrimina meglio densità basse vs alte
            - metro_lines×2 (non ×5): tram è mezzo primario a Milano
            - pct_employed rimosso: in centro misura chi ci abita, non qualità
            - Vacancy con floor 15% e peso -1%: sfitto centrale = investimento/Airbnb

          Fonti: OSM, ISTAT 2023, OMI, Sentinel-2, Comune di Milano open data
        """
        m = self.master

        # --- Eligibility: only score neighborhoods with real urban fabric ---
        poi_ok = m["poi_count"].fillna(0) >= 30 if "poi_count" in m.columns else True
        pop_ok = m["pop_tot"].fillna(0) >= 2000 if "pop_tot" in m.columns else True
        eligible = poi_ok & pop_ok

        # --- Non-linear density: asymmetric sigmoid ---
        if "poi_density" in m.columns:
            d = m["poi_density"].fillna(0)
            m["density_curve"] = 1 - np.exp(-d / 20)

        # --- Essential services PER CAPITA ---
        if "poi_share_essential_services" in m.columns and "poi_density" in m.columns:
            m["essential_per_1000"] = m["poi_density"] * m["poi_share_essential_services"]
            m["pctl_essential_pc"] = m["essential_per_1000"].rank(pct=True)

        # --- Transit connectivity (NOT per-capita!) ---
        # metro_lines×2 + tpl_lines: tram is a primary mode in Milan
        if "metro_lines" in m.columns and "tpl_lines" in m.columns:
            m["connectivity"] = m["metro_lines"].fillna(0) * 2 + m["tpl_lines"].fillna(0)
            m["pctl_connectivity"] = m["connectivity"].rank(pct=True)

        # --- Sport facilities (log to dampen outliers) ---
        if "sport_facilities" in m.columns:
            m["sport_log"] = np.log1p(m["sport_facilities"].fillna(0))
            m["pctl_sport"] = m["sport_log"].rank(pct=True)

        # --- Park area per capita (capped at 10 mq/ab) ---
        if "park_mq_per_capita" in m.columns:
            park_adj = m["park_mq_per_capita"].fillna(0).clip(upper=10)
            m["pctl_park"] = park_adj.rank(pct=True)

        # --- Aging penalty ---
        if "aging_index" in m.columns:
            m["pctl_aging"] = m["aging_index"].rank(pct=True)

        # --- NDVI with diminishing returns (cap at 0.30) ---
        if "ndvi_mean" in m.columns:
            ndvi_adj = m["ndvi_mean"].fillna(0).clip(upper=0.30)
            m["ndvi_adj_pctl"] = ndvi_adj.rank(pct=True)

        # --- Builtup with floor (0.15) ---
        if "builtup_mean" in m.columns:
            built_adj = m["builtup_mean"].fillna(0.5).clip(lower=0.15)
            m["builtup_adj_pctl"] = built_adj.rank(pct=True)

        # --- Vacancy with floor at 15% (below is physiological) ---
        if "pct_housing_empty" in m.columns:
            vacancy_excess = (m["pct_housing_empty"].fillna(0.15) - 0.15).clip(lower=0)
            m["pctl_vacancy_excess"] = vacancy_excess.rank(pct=True)

        # --- Build quality composite (only for eligible NIL) ---
        raw = pd.Series(0.0, index=m.index)

        # OFFERTA COMMERCIALE (42%)
        if "pctl_poi_entropy" in m.columns:
            raw += m["pctl_poi_entropy"].fillna(0.5) * 0.20
        if "pctl_essential_pc" in m.columns:
            raw += m["pctl_essential_pc"].fillna(0.5) * 0.12
        if "density_curve" in m.columns:
            raw += m["density_curve"].fillna(0.0) * 0.10

        # ACCESSIBILITÀ (17%)
        if "pctl_connectivity" in m.columns:
            raw += m["pctl_connectivity"].fillna(0.5) * 0.17

        # SERVIZI PUBBLICI (6%)
        if "pctl_sport" in m.columns:
            raw += m["pctl_sport"].fillna(0.5) * 0.03
        if "pctl_park" in m.columns:
            raw += m["pctl_park"].fillna(0.5) * 0.03

        # AMBIENTE (8%)
        if "ndvi_adj_pctl" in m.columns:
            raw += m["ndvi_adj_pctl"].fillna(0.5) * 0.05
        if "builtup_adj_pctl" in m.columns:
            raw -= m["builtup_adj_pctl"].fillna(0.5) * 0.02
        if "pctl_vacancy_excess" in m.columns:
            raw -= m["pctl_vacancy_excess"].fillna(0.5) * 0.01

        # STRUTTURA (-2%) — solo invecchiamento
        if "pctl_aging" in m.columns:
            raw -= m["pctl_aging"].fillna(0.5) * 0.02

        # Min-max normalize to 0-100 (only eligible NIL)
        quality = pd.Series(np.nan, index=m.index)
        raw_elig = raw[eligible]
        if len(raw_elig) > 1:
            lo, hi = raw_elig.min(), raw_elig.max()
            if hi > lo:
                quality[eligible] = ((raw_elig - lo) / (hi - lo) * 100).round(1)
            else:
                quality[eligible] = 50.0
        m["quality_score"] = quality

        # Price percentile (inverted: lower price = more affordable = higher value)
        if "price_sqm" in m.columns:
            price_pctl = m["price_sqm"].rank(pct=True)
            m["price_pctl"] = price_pctl

            # Value = quality relative to price tier
            # A neighborhood scores high if quality_percentile >> price_percentile
            m["value_score"] = quality - (price_pctl * 100)
            # Normalize to 0-100
            vs = m["value_score"]
            m["value_score"] = ((vs - vs.min()) / (vs.max() - vs.min()) * 100).round(1)
        else:
            m["value_score"] = quality

        self.master = m

    # ------------------------------------------------------------------
    # LENS 2: IDENTITY — "Chi vive qui?"
    # ------------------------------------------------------------------

    def _compute_identity(self):
        """Assign rich typology based on statistical clustering of features."""
        m = self.master

        identities = {}
        for nil_id in m.index:
            row = m.loc[nil_id]
            pc = row.get("poi_count", 0) or 0
            pop = row.get("pop_tot", 0) or 0
            price = row.get("price_sqm", 0) or 0
            prem = row.get("poi_premium_share", 0) or 0
            ent = row.get("poi_entropy", 0) or 0
            pct_ter = row.get("pct_tertiary", 0) or 0
            pct_for = row.get("pct_foreign", 0) or 0
            pct_old = row.get("pct_old", 0) or 0
            pct_young = row.get("pct_young", 0) or 0
            aging = row.get("aging_index", 0) or 0
            ndvi = row.get("ndvi_mean", 0) or 0
            density = row.get("poi_density", 0) or 0
            rpp = row.get("residents_per_poi", 999) or 999
            single = row.get("pct_single_hh", 0) or 0
            empty = row.get("pct_housing_empty", 0) or 0
            val_score = row.get("value_score", 50) or 50

            # Primary type (mutually exclusive)
            if price > 7000 and prem > 0.25:
                primary = "Lusso"
                emoji = "💎"
            elif price > 5500 and pct_ter > 0.35:
                primary = "Borghese colto"
                emoji = "🎓"
            elif pc > 400 and density > 30:
                primary = "Hub commerciale"
                emoji = "🏪"
            elif pct_for > 0.30 and pc > 50:
                primary = "Multiculturale"
                emoji = "🌍"
            elif ndvi > 0.35 and pop > 5000:
                primary = "Verde residenziale"
                emoji = "🌳"
            elif aging > 2.5 and pop > 5000:
                primary = "Storico consolidato"
                emoji = "🏛️"
            elif pct_young > 0.18 and single > 0.55:
                primary = "Giovane e dinamico"
                emoji = "⚡"
            elif pop > 20000 and pc > 100:
                primary = "Quartiere popolare attivo"
                emoji = "🏘️"
            elif pop > 10000:
                primary = "Residenziale"
                emoji = "🏠"
            elif pop < 3000 and pc < 30:
                primary = "Periferico"
                emoji = "📍"
            else:
                primary = "Misto"
                emoji = "🔀"

            # Secondary tags (can be multiple)
            tags = []
            if val_score > 70 and pc > MIN_POI_SIGNIFICANT:
                tags.append("buon rapporto qualità-prezzo")
            if val_score < 30 and price > 5000:
                tags.append("sopravvalutato")
            if prem > 0.30 and pc > MIN_POI_SIGNIFICANT:
                tags.append("offerta premium")
            if ent > 0.75 and pc > 50:
                tags.append("mix funzionale ricco")
            if empty > 0.20:
                tags.append("alta sfittanza")
            if rpp > 80 and pop > 5000:
                tags.append("sottoservito")
            if rpp < 20 and pc > 100:
                tags.append("polo attrattore")

            identities[nil_id] = {
                "primary": primary,
                "emoji": emoji,
                "tags": tags,
            }

        self.identities = identities

    # ------------------------------------------------------------------
    # LENS 3: SIGNALS — "Dove sta andando?"
    # ------------------------------------------------------------------

    def _compute_signals(self):
        """
        Cross-sectional signals of transformation.
        NOT based on OSM time-series (unreliable).
        Based on: price trends (OMI, reliable), demographic structure,
        supply-demand gaps, comparison to similar neighborhoods.
        """
        m = self.master
        self.signals = {}

        for nil_id in m.index:
            row = m.loc[nil_id]
            sigs = []

            pc = row.get("poi_count", 0) or 0
            pop = row.get("pop_tot", 0) or 0
            price = row.get("price_sqm", 0) or 0
            p5y = row.get("price_change_5y")
            p10y = row.get("price_change_10y")
            prem = row.get("poi_premium_share", 0) or 0
            pct_ter = row.get("pct_tertiary", 0) or 0
            pct_for = row.get("pct_foreign", 0) or 0
            pct_young = row.get("pct_young", 0) or 0
            pct_old = row.get("pct_old", 0) or 0
            aging = row.get("aging_index", 0) or 0
            rpp = row.get("residents_per_poi", 999) or 999
            empty = row.get("pct_housing_empty", 0) or 0
            val_score = row.get("value_score", 50) or 50
            fascia = row.get("fascia", "")

            # --- Price-based signals (RELIABLE — OMI data) ---
            if p5y is not None and not (isinstance(p5y, float) and math.isnan(p5y)):
                city_avg_5y = m["price_change_5y"].median()
                if p5y > city_avg_5y + 0.10:
                    sigs.append({
                        "type": "price_boom",
                        "icon": "📈",
                        "label": "Prezzi in forte crescita",
                        "detail": f"+{p5y*100:.0f}% in 5 anni (media città: +{city_avg_5y*100:.0f}%)",
                        "severity": "high",
                        "source": "OMI - Agenzia delle Entrate",
                    })
                elif p5y < city_avg_5y - 0.05:
                    sigs.append({
                        "type": "price_stagnation",
                        "icon": "📉",
                        "label": "Prezzi sotto la media",
                        "detail": f"+{p5y*100:.0f}% in 5 anni vs +{city_avg_5y*100:.0f}% media città",
                        "severity": "medium",
                        "source": "OMI - Agenzia delle Entrate",
                    })

            # --- Gentrification signal: price rising + high education + multicultural ---
            if (p5y is not None and not (isinstance(p5y, float) and math.isnan(p5y))
                    and p5y > 0.20 and pct_ter > 0.25 and pct_for > 0.15
                    and fascia in ("D", "E")):
                sigs.append({
                    "type": "gentrification",
                    "icon": "🔄",
                    "label": "Segnale di gentrificazione",
                    "detail": f"Periferia con prezzi +{p5y*100:.0f}% e {pct_ter*100:.0f}% laureati",
                    "severity": "high",
                    "source": "Incrocio OMI + ISTAT",
                })

            # --- Demographic pressure: young population + high density ---
            if pct_young > 0.17 and rpp < 40 and pop > 10000:
                sigs.append({
                    "type": "youth_hub",
                    "icon": "👥",
                    "label": "Polo giovani e servizi",
                    "detail": f"{pct_young*100:.0f}% sotto i 19 anni, {int(rpp)} residenti per attività",
                    "severity": "medium",
                    "source": "ISTAT 2023",
                })

            # --- Aging risk: very old population + low services ---
            if aging > 3 and rpp > 60:
                sigs.append({
                    "type": "aging_risk",
                    "icon": "⚠️",
                    "label": "Rischio invecchiamento",
                    "detail": f"Indice vecchiaia {aging:.1f} e solo 1 attività ogni {int(rpp)} residenti",
                    "severity": "high",
                    "source": "ISTAT 2023",
                })

            # --- Undervalued: high quality, low price ---
            if val_score > 75 and pc >= MIN_POI_SIGNIFICANT:
                sigs.append({
                    "type": "undervalued",
                    "icon": "💡",
                    "label": "Quartiere sottovalutato",
                    "detail": f"Qualità percepita alta (top {100-val_score:.0f}%) a prezzi accessibili",
                    "severity": "high",
                    "source": "Analisi composita",
                })

            # --- Supply-demand gaps ---
            if pop > 10000 and pc >= MIN_POI_SIGNIFICANT:
                cat_shares = {}
                for c in m.columns:
                    if c.startswith("poi_share_"):
                        cat_id = c.replace("poi_share_", "")
                        v = row.get(c, 0) or 0
                        if v > 0:
                            cat_shares[cat_id] = v

                # Compare to city median
                gaps = []
                for cat_id, share in cat_shares.items():
                    col = f"poi_share_{cat_id}"
                    city_med = m[col].median()
                    if city_med > 0 and share < city_med * 0.5 and pc > 50:
                        gap_pct = (1 - share / city_med) * 100
                        gaps.append({
                            "category": cat_id,
                            "name": CAT_LABELS.get(cat_id, cat_id),
                            "gap_pct": gap_pct,
                            "nil_share": share,
                            "city_median": city_med,
                        })

                gaps.sort(key=lambda x: x["gap_pct"], reverse=True)
                if gaps:
                    top_gap = gaps[0]
                    sigs.append({
                        "type": "supply_gap",
                        "icon": "🎯",
                        "label": f"Carenza: {top_gap['name']}",
                        "detail": (
                            f"{top_gap['nil_share']*100:.0f}% vs {top_gap['city_median']*100:.0f}% "
                            f"media città (gap {top_gap['gap_pct']:.0f}%)"
                        ),
                        "severity": "medium",
                        "source": "OpenStreetMap 2026",
                    })

            self.signals[nil_id] = sigs

    # ------------------------------------------------------------------
    # LENS 4: STRATEGIC INTELLIGENCE — Decisioni di investimento
    # ------------------------------------------------------------------

    def _compute_strategic_scores(self):
        """
        Actionable intelligence for entrepreneurs and investors.

        1. INVESTMENT ATTRACTIVENESS INDEX (IAI)
           Composite: price momentum + demographic vitality + service gaps
           → "Dove conviene investire in immobili?"

        2. COMMERCIAL OPPORTUNITY SCORE (COS) per category
           Demand proxy (demographics) vs supply (current POI)
           → "Che tipo di attività aprire e dove?"

        3. CATCHMENT POWER
           How many residents + commuters a location can capture
           → "Qual è il bacino d'utenza reale?"
        """
        m = self.master

        # ---- 1. Investment Attractiveness Index ----
        # Components (all as percentile ranks, 0-1):
        iai_components = {}

        # a) Price momentum (OMI 5-year change) — weight 0.25
        if "pctl_price_change_5y" not in m.columns and "price_change_5y" in m.columns:
            m["pctl_price_change_5y"] = m["price_change_5y"].rank(pct=True)
        iai_components["pctl_price_change_5y"] = 0.25

        # b) Demographic vitality — weight 0.20
        # (younger + more employed + growing education = more vital)
        demo_vital = pd.Series(0.0, index=m.index)
        for col, w in [("pct_young", 0.4), ("pct_employed", 0.3), ("pct_tertiary", 0.3)]:
            pctl = f"pctl_{col}"
            if pctl in m.columns:
                demo_vital += m[pctl].fillna(0.5) * w
        m["demo_vitality"] = demo_vital.rank(pct=True)
        iai_components["demo_vitality"] = 0.20

        # c) Service gap intensity — weight 0.20
        # High residents_per_poi = underserved = opportunity
        if "pctl_residents_per_poi" in m.columns:
            iai_components["pctl_residents_per_poi"] = 0.20  # high = underserved = attractive

        # d) Affordability (inverse price) — weight 0.15
        if "price_sqm" in m.columns:
            m["affordability"] = 1 - m["price_sqm"].rank(pct=True)
            iai_components["affordability"] = 0.15

        # e) Green & livability — weight 0.10
        if "pctl_ndvi_mean" in m.columns:
            iai_components["pctl_ndvi_mean"] = 0.10

        # f) Low vacancy (housing) — weight 0.10
        if "pct_housing_empty" in m.columns:
            m["low_vacancy"] = 1 - m["pct_housing_empty"].rank(pct=True)
            iai_components["low_vacancy"] = 0.10

        # Compute IAI
        iai = pd.Series(0.0, index=m.index)
        total_weight = 0
        for col, w in iai_components.items():
            if col in m.columns:
                iai += m[col].fillna(0.5) * w
                total_weight += w

        if total_weight > 0:
            iai = iai / total_weight
            m["iai_score"] = (iai.rank(pct=True) * 100).round(1)
        else:
            m["iai_score"] = 50.0

        # ---- 2. Commercial Opportunity Score per category ----
        self.commercial_opportunities = {}

        # Demand proxies by category
        demand_profiles = {
            "hospitality_tourism": {
                "drivers": [("pop_tot", 0.3), ("pct_tertiary", 0.25), ("pct_young", 0.2), ("poi_density", 0.25)],
                "name": "Ristorazione e turismo",
                "description": "Bar, ristoranti, hotel, food delivery",
                "min_pop": 5000,
            },
            "lifestyle": {
                "drivers": [("pct_tertiary", 0.35), ("pct_young", 0.25), ("price_sqm", 0.2), ("pct_employed", 0.2)],
                "name": "Lifestyle e benessere",
                "description": "Palestre, spa, centri yoga, barbershop premium",
                "min_pop": 5000,
            },
            "retail_premium": {
                "drivers": [("price_sqm", 0.4), ("pct_tertiary", 0.3), ("poi_density", 0.15), ("pct_employed", 0.15)],
                "name": "Commercio premium",
                "description": "Boutique, design, enoteche, specialty food",
                "min_pop": 3000,
            },
            "essential_services": {
                "drivers": [("pop_tot", 0.3), ("pct_old", 0.3), ("residents_per_poi", 0.2), ("pct_foreign", 0.2)],
                "name": "Servizi essenziali",
                "description": "Farmacie, studi medici, servizi alla persona",
                "min_pop": 8000,
            },
            "retail_base": {
                "drivers": [("pop_tot", 0.4), ("residents_per_poi", 0.3), ("pct_foreign", 0.15), ("pct_old", 0.15)],
                "name": "Negozi di vicinato",
                "description": "Alimentari, ferramenta, cartolerie, edicole",
                "min_pop": 5000,
            },
        }

        for cat_id, profile in demand_profiles.items():
            share_col = f"poi_share_{cat_id}"
            if share_col not in m.columns:
                continue

            # Compute demand score (percentile of weighted drivers)
            demand = pd.Series(0.0, index=m.index)
            for col, w in profile["drivers"]:
                if col in m.columns:
                    demand += m[col].rank(pct=True).fillna(0.5) * w

            demand = demand.rank(pct=True)

            # Supply score (current share, inverted: low supply = high opportunity)
            supply = m[share_col].rank(pct=True)
            supply_inv = 1 - supply

            # Opportunity = demand * (1 - supply) — high demand + low supply
            opp = (demand * 0.6 + supply_inv * 0.4).rank(pct=True) * 100

            # Filter: only where population is sufficient
            min_pop = profile["min_pop"]
            opp = opp.where(m["pop_tot"] >= min_pop, other=np.nan)
            opp = opp.where(m["is_significant"], other=np.nan)

            # Store per-NIL
            m[f"opp_{cat_id}"] = opp.round(1)

            # Top 10 opportunities
            top10 = opp.dropna().nlargest(10)
            self.commercial_opportunities[cat_id] = {
                "name": profile["name"],
                "description": profile["description"],
                "top": [
                    {
                        "nil_id": int(nid),
                        "name": self.nil_names.get(nid, str(nid)),
                        "score": round(float(val), 1),
                        "price_sqm": _fmt_eur(m.loc[nid, "price_sqm"]) if nid in m.index else None,
                        "pop": int(m.loc[nid, "pop_tot"]) if nid in m.index else 0,
                        "current_share": _safe(m.loc[nid, share_col]) if nid in m.index else None,
                        "city_median": _safe(m[share_col].median()),
                    }
                    for nid, val in top10.items()
                ],
            }

        # ---- 3. Catchment Power ----
        # Effective demand = residents + commercial density (proxy for commuters/visitors)
        if "poi_density" in m.columns:
            m["catchment_residents"] = m["pop_tot"].fillna(0)
            # High POI density = attracts visitors beyond residents
            m["catchment_multiplier"] = 1 + (m["poi_density"].rank(pct=True) * 0.5)
            m["catchment_effective"] = (m["catchment_residents"] * m["catchment_multiplier"]).round(0)

        self.master = m

    # ------------------------------------------------------------------
    # City summary
    # ------------------------------------------------------------------

    def _compute_city_summary(self):
        m = self.master
        sig = m[m["is_significant"]]

        self.city_summary = {
            "n_nil": len(self.nil_names),
            "total_poi": int(m["poi_count"].sum()),
            "total_pop": int(m["pop_tot"].sum()),
            "avg_price_sqm": _fmt_eur(m["price_sqm"].mean()),
            "median_price_sqm": _fmt_eur(m["price_sqm"].median()),
            "price_range": [_fmt_eur(m["price_sqm"].min()), _fmt_eur(m["price_sqm"].max())],
            "avg_premium": _safe(sig["poi_premium_share"].mean()),
            "avg_entropy": _safe(sig["poi_entropy"].mean()),
            "avg_price_change_5y": _safe(m["price_change_5y"].median()),
        }

    # ------------------------------------------------------------------
    # API Methods
    # ------------------------------------------------------------------

    def get_quarters(self) -> list:
        """Return list but we only use latest."""
        return self.quarters

    def get_overview(self) -> dict:
        return self.city_summary

    def get_rankings(self) -> dict:
        """Multiple ranking views."""
        m = self.master
        sig = m[m["is_significant"]]

        rankings = {}

        ranking_defs = {
            "value_score": ("Miglior rapporto qualità-prezzo", False, sig),
            "iai_score": ("Più attrattivo per investimenti", False, sig),
            "price_sqm": ("Più costosi (EUR/mq)", False, m),
            "quality_score": ("Migliore qualità della vita", False, sig),
            "poi_entropy": ("Più diversificato", False, sig),
            "poi_density": ("Più servizi per abitante", False, sig),
            "price_change_5y": ("Prezzi in maggiore crescita", False, m[m["price_change_5y"].notna()]),
            "residents_per_poi": ("Meno servito", True, sig),
            "pct_foreign": ("Più multiculturale", False, m[m["pop_tot"] > 3000]),
            "pct_tertiary": ("Più istruito", False, m[m["pop_tot"] > 3000]),
        }

        for metric, (label, ascending, subset) in ranking_defs.items():
            if metric not in subset.columns:
                continue
            valid = subset[metric].dropna()
            if len(valid) < 5:
                continue
            ranked = valid.sort_values(ascending=ascending)
            top10 = []
            for nil_id, val in ranked.head(10).items():
                name = self.nil_names.get(nil_id, str(nil_id))
                identity = self.identities.get(nil_id, {})
                top10.append({
                    "nil_id": nil_id,
                    "name": name,
                    "value": _safe(val),
                    "type": identity.get("primary", ""),
                    "emoji": identity.get("emoji", ""),
                })
            rankings[metric] = {"label": label, "top": top10}

        return rankings

    def get_map_data(self, year_quarter: str, layer: str) -> dict:
        """GeoJSON for choropleth. Uses master (latest snapshot)."""
        m = self.master
        features = []

        for nil_id, geom in self.nil_geom.items():
            row = m.loc[nil_id] if nil_id in m.index else pd.Series()
            identity = self.identities.get(nil_id, {})

            props = {
                "nil_id": nil_id,
                "name": self.nil_names.get(nil_id, ""),
                "type": identity.get("primary", ""),
                "emoji": identity.get("emoji", ""),
                "tags": identity.get("tags", []),
                # POI
                "poi_count": _safe(row.get("poi_count")),
                "premium": _safe(row.get("poi_premium_share")),
                "entropy": _safe(row.get("poi_entropy")),
                "poi_density": _safe(row.get("poi_density")),
                "residents_per_poi": _safe(row.get("residents_per_poi")),
                # Census
                "pop": _safe(row.get("pop_tot")),
                "pct_foreign": _safe(row.get("pct_foreign")),
                "pct_old": _safe(row.get("pct_old")),
                "pct_young": _safe(row.get("pct_young")),
                "pct_tertiary": _safe(row.get("pct_tertiary")),
                "aging_index": _safe(row.get("aging_index")),
                # Prices
                "price_sqm": _fmt_eur(row.get("price_sqm")),
                "price_min": _fmt_eur(row.get("price_min")),
                "price_max": _fmt_eur(row.get("price_max")),
                "price_change_5y": _safe(row.get("price_change_5y")),
                "price_change_10y": _safe(row.get("price_change_10y")),
                # Scores
                "quality_score": _safe(row.get("quality_score")),
                "value_score": _safe(row.get("value_score")),
                "iai_score": _safe(row.get("iai_score")),
                # Satellite
                "ndvi": _safe(row.get("ndvi_mean")),
                # Infrastructure (Comune di Milano)
                "connectivity": _safe(row.get("connectivity")),
                "metro_stops": _safe(row.get("metro_stops")),
                "metro_lines": _safe(row.get("metro_lines")),
                "tpl_lines": _safe(row.get("tpl_lines")),
                "sport_facilities": _safe(row.get("sport_facilities")),
                "park_mq_per_capita": _safe(row.get("park_mq_per_capita")),
                # Significance
                "significant": bool(row.get("is_significant", False)),
            }

            features.append({
                "type": "Feature",
                "properties": props,
                "geometry": geom,
            })

        return {"type": "FeatureCollection", "features": features}

    def get_nil_detail(self, nil_id: int) -> dict:
        """Full neighborhood deep-dive."""
        if nil_id not in self.master.index:
            return {"nil_id": nil_id, "name": self.nil_names.get(nil_id, str(nil_id))}

        row = self.master.loc[nil_id]
        name = self.nil_names.get(nil_id, str(nil_id))
        identity = self.identities.get(nil_id, {})
        sigs = self.signals.get(nil_id, [])

        pc = int(row.get("poi_count", 0) or 0)
        pop = int(row.get("pop_tot", 0) or 0)
        price = row.get("price_sqm")

        # --- Category breakdown ---
        categories = []
        share_cols = [c for c in self.master.columns if c.startswith("poi_share_")]
        for c in share_cols:
            v = row.get(c)
            if v and not (isinstance(v, float) and np.isnan(v)) and v > 0.005:
                cat_id = c.replace("poi_share_", "")
                # Compare to city median
                city_med = self.master[c].median()
                categories.append({
                    "id": cat_id,
                    "name": CAT_LABELS.get(cat_id, cat_id),
                    "value": round(float(v), 4),
                    "city_median": round(float(city_med), 4),
                    "delta": round(float(v - city_med), 4),
                })
        categories.sort(key=lambda x: x["value"], reverse=True)

        # --- Price history (from OMI — this IS reliable) ---
        price_history = None
        pts = self.price_ts[self.price_ts["nil_id"] == nil_id].sort_values("semester")
        if not pts.empty:
            price_history = {
                "semesters": pts["semester"].tolist(),
                "prices": [_fmt_eur(v) for v in pts["price_sqm"]],
            }

        # --- Comparable neighborhoods (similar price tier) ---
        comparables = self._find_comparables(nil_id)

        # --- Radar profile (percentile ranks for key metrics) ---
        radar = {}
        radar_metrics = {
            "poi_density": "Servizi",
            "poi_entropy": "Diversità",
            "transit_per_1000": "Trasporti",
            "pct_tertiary": "Istruzione",
            "ndvi_mean": "Verde",
            "price_sqm": "Prezzo",
        }
        for metric, label in radar_metrics.items():
            pctl_col = f"pctl_{metric}"
            if pctl_col in self.master.columns:
                v = row.get(pctl_col)
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    radar[label] = round(float(v) * 100, 0)

        # --- Summary stats ---
        summary = {
            "poi_count": pc,
            "pop": pop,
            "price_sqm": _fmt_eur(price),
            "price_min": _fmt_eur(row.get("price_min")),
            "price_max": _fmt_eur(row.get("price_max")),
            "price_change_5y": _safe(row.get("price_change_5y")),
            "price_change_10y": _safe(row.get("price_change_10y")),
            "premium": _safe(row.get("poi_premium_share")),
            "entropy": _safe(row.get("poi_entropy")),
            "poi_density": _safe(row.get("poi_density")),
            "residents_per_poi": _safe(row.get("residents_per_poi")),
            "quality_score": _safe(row.get("quality_score")),
            "value_score": _safe(row.get("value_score")),
            "pct_foreign": _safe(row.get("pct_foreign")),
            "pct_tertiary": _safe(row.get("pct_tertiary")),
            "pct_old": _safe(row.get("pct_old")),
            "pct_young": _safe(row.get("pct_young")),
            "aging_index": _safe(row.get("aging_index")),
            "pct_housing_empty": _safe(row.get("pct_housing_empty")),
            "ndvi": _safe(row.get("ndvi_mean")),
            # Infrastructure (Comune di Milano)
            "connectivity": _safe(row.get("connectivity")),
            "metro_stops": _safe(row.get("metro_stops")),
            "metro_lines": _safe(row.get("metro_lines")),
            "tpl_lines": _safe(row.get("tpl_lines")),
            "sport_facilities": _safe(row.get("sport_facilities")),
            "park_mq_per_capita": _safe(row.get("park_mq_per_capita")),
        }

        # --- Narrative ---
        narrative = self._build_narrative(nil_id, name, row, identity, categories)

        # --- Strategic scores ---
        strategic = {
            "iai_score": _safe(row.get("iai_score")),
            "catchment_effective": int(row.get("catchment_effective", 0) or 0),
            "catchment_multiplier": _safe(row.get("catchment_multiplier")),
        }

        # Category-specific opportunity scores for this NIL
        cat_opps = []
        for cat_id in ["hospitality_tourism", "lifestyle", "retail_premium", "essential_services", "retail_base"]:
            opp_col = f"opp_{cat_id}"
            if opp_col in self.master.columns:
                v = row.get(opp_col)
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    share_col = f"poi_share_{cat_id}"
                    cat_opps.append({
                        "category": cat_id,
                        "name": CAT_LABELS.get(cat_id, cat_id),
                        "score": round(float(v), 1),
                        "current_share": _safe(row.get(share_col)),
                        "city_median": _safe(self.master[share_col].median()) if share_col in self.master.columns else None,
                    })
        cat_opps.sort(key=lambda x: x["score"], reverse=True)
        strategic["opportunities"] = cat_opps

        return {
            "nil_id": nil_id,
            "name": name,
            "identity": identity,
            "summary": summary,
            "categories": categories,
            "signals": sigs,
            "price_history": price_history,
            "comparables": comparables,
            "radar": radar,
            "narrative": narrative,
            "strategic": strategic,
        }

    # ------------------------------------------------------------------
    # Narrative v2: insight-driven, statistically grounded
    # ------------------------------------------------------------------

    def _build_narrative(self, nil_id, name, row, identity, categories):
        """Generate rich, insight-driven Italian narrative."""
        parts = []
        m = self.master

        pc = int(row.get("poi_count", 0) or 0)
        pop = int(row.get("pop_tot", 0) or 0)
        price = row.get("price_sqm")
        p5y = row.get("price_change_5y")
        prem = row.get("poi_premium_share", 0) or 0
        ent = row.get("poi_entropy", 0) or 0
        rpp = row.get("residents_per_poi", 999) or 999
        pct_ter = row.get("pct_tertiary", 0) or 0
        pct_for = row.get("pct_foreign", 0) or 0
        aging = row.get("aging_index", 0) or 0
        val_score = row.get("value_score", 50) or 50
        quality = row.get("quality_score", 50) or 50
        ndvi = row.get("ndvi_mean", 0) or 0

        # Identity opening
        emoji = identity.get("emoji", "")
        primary = identity.get("primary", "")
        parts.append(f"{emoji} {name} è un quartiere {primary.lower()}")

        # Population + price context
        if pop > 0 and price:
            price_pctl = row.get("pctl_price_sqm", 0.5) or 0.5
            if price_pctl > 0.8:
                parts.append(
                    f"Con {pop:,} abitanti e un prezzo medio di {int(price):,} EUR/mq, "
                    f"è tra i quartieri più costosi di Milano"
                )
            elif price_pctl < 0.2:
                parts.append(
                    f"Con {pop:,} abitanti e un prezzo medio di {int(price):,} EUR/mq, "
                    f"è tra le zone più accessibili della città"
                )
            else:
                parts.append(
                    f"Con {pop:,} abitanti e un prezzo medio di {int(price):,} EUR/mq"
                )

        # Price trend (OMI = reliable)
        if p5y is not None and not (isinstance(p5y, float) and math.isnan(p5y)):
            city_med = m["price_change_5y"].median()
            if p5y > city_med + 0.10:
                parts.append(
                    f"I prezzi sono cresciuti del {p5y*100:.0f}% in cinque anni, "
                    f"ben sopra la media cittàdina (+{city_med*100:.0f}%): "
                    f"un segnale di forte attrattività"
                )
            elif p5y > city_med:
                parts.append(
                    f"I prezzi sono cresciuti del {p5y*100:.0f}% in cinque anni, "
                    f"leggermente sopra la media (+{city_med*100:.0f}%)"
                )
            elif p5y > 0:
                parts.append(
                    f"La crescita dei prezzi ({p5y*100:.0f}% in 5 anni) è inferiore "
                    f"alla media cittàdina (+{city_med*100:.0f}%)"
                )

        # Value analysis
        if pc >= MIN_POI_SIGNIFICANT:
            if val_score > 70:
                parts.append(
                    f"Il rapporto qualità-prezzo è eccellente: "
                    f"la qualità dei servizi è superiore a quanto ci si aspetterebbe dalla fascia di prezzo"
                )
            elif val_score < 30:
                parts.append(
                    f"Il rapporto qualità-prezzo è sotto la media: "
                    f"il prezzo riflette più la posizione che la qualità dei servizi disponibili"
                )

        # Commercial character (only if significant)
        if pc >= MIN_POI_SIGNIFICANT:
            if rpp < 25:
                parts.append(
                    f"Con {pc} attività e solo {int(rpp)} residenti per esercizio, "
                    f"è un polo attrattore che serve anche chi non ci abita"
                )
            elif rpp > 80:
                parts.append(
                    f"Con {int(rpp)} residenti per attività commerciale, "
                    f"è una zona poco servita rispetto alla popolazione"
                )

            if prem > 0.30:
                parts.append(
                    f"L'offerta commerciale è decisamente premium "
                    f"({prem*100:.0f}% delle attività, vs {m['poi_premium_share'].median()*100:.0f}% media città)"
                )

        # Key demographic insight
        if pct_for > 0.30:
            parts.append(
                f"Quartiere fortemente multiculturale con {pct_for*100:.0f}% di residenti stranieri"
            )
        if aging > 3:
            parts.append(
                f"La popolazione è tra le più anziane di Milano "
                f"(indice di vecchiaia {aging:.1f}, media città {m['aging_index'].median():.1f})"
            )

        return ". ".join(parts) + "."

    # ------------------------------------------------------------------
    # Find comparable neighborhoods
    # ------------------------------------------------------------------

    def _find_comparables(self, nil_id, n=4):
        """Find most similar NILs by price tier + demographics."""
        if nil_id not in self.master.index:
            return []

        row = self.master.loc[nil_id]
        m = self.master

        # Features for comparison
        features = ["price_sqm", "poi_density", "pct_tertiary", "pct_foreign", "aging_index"]
        valid_cols = [c for c in features if c in m.columns]

        # Normalize
        sub = m[valid_cols].copy()
        for c in valid_cols:
            mu, sigma = sub[c].mean(), sub[c].std()
            if sigma > 0:
                sub[c] = (sub[c] - mu) / sigma
            else:
                sub[c] = 0

        # Euclidean distance
        target = sub.loc[nil_id]
        dists = ((sub - target) ** 2).sum(axis=1).apply(np.sqrt)
        dists = dists.drop(nil_id, errors="ignore")
        nearest = dists.nsmallest(n)

        result = []
        for nid, dist in nearest.items():
            r = self.master.loc[nid]
            result.append({
                "nil_id": int(nid),
                "name": self.nil_names.get(nid, str(nid)),
                "price_sqm": _fmt_eur(r.get("price_sqm")),
                "poi_count": int(r.get("poi_count", 0) or 0),
                "similarity": round(1 / (1 + dist), 2),
            })

        return result
