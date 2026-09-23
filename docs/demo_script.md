# Demo Script — Cascading Delay Intelligence

Time: ~10 minutes. All commands run from the repo root. Every number below
was observed live on the deterministic showcase dataset (seed 42).

## 0. Setup (once)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

## 1. Problem (30 seconds, say this)

> "A logistics company tracks shipment scans, delay reports, and warehouse
> transfers separately, making it impossible to predict which operational
> routes consistently produce cascading delivery delays. This product joins
> those three sources into one journey per shipment, finds cascades —
> an initial delay followed by downstream delay(s) — and shows which
> routes repeat the pattern."

## 2. Data sources (1 minute)

Three separate raw sources, provenance kept per row (`source_file`,
`source_row_id`):

```bash
python -m pipeline.run_pipeline --dataset showcase
```

Expected console output (10 staged steps, timings vary):

```text
[1/10] Ingestion ........ SUCCESS     # 8,870 scans + 990 delays + 1,233 transfers
[2/10] Validation ...... WARNING      # honest WARNING: 35% of scan rows lack warehouse_id
[3/10] Cleaning ........ SUCCESS      # 0 rows removed, raw files untouched
[4/10] Integration ..... SUCCESS      # scans LEFT JOIN delays LEFT JOIN transfers → 8,870 rows
[5/10] Analytics ....... SUCCESS      # 3,000 shipments, 990 delayed (33.0%)
[6/10] SQL ............. SUCCESS      # 15/15 SQL-vs-Pandas comparisons match
[7/10] Cascade ......... SUCCESS      # 602 cascade candidates of 3,000 checked
[8/10] Route Risk ...... SUCCESS      # top: R2 at 70.5% historical cascade rate
[9/10] Prediction ...... SUCCESS      # baseline trained, test ROC-AUC ~0.77
[10/10] Alerts ......... SUCCESS      # 1,277 alerts, zero unavailable checks
```

Note the run ID in the last line, e.g. `Manifest:
data/processed/runs/run_20260923T055827_9f04eb0a.json` — every later
command uses that file. Point out: a validation `ERROR` would stop the
run before cleaning (gate), and the manifest still records the failure.

## 3. Data integration (30 seconds)

One integrated journey table, no invented keys:

- Base: scans (`shipment_id`), `LEFT JOIN` delays, `LEFT JOIN` transfers.
- Unmatched rows preserved and counted; `temporal_violations: 0`.
- Output: `data/processed/integrated_logistics_showcase.csv` (8,870 rows).

## 4. Cascade detection (1 minute)

Definition (no hidden thresholds, associational language only): an
**initial delay followed by later downstream delay(s)** in one shipment's
timestamp-ordered journey. A single delay is never a cascade.

- 3,000 journeys checked → **602 cascade candidates (20.1%)**,
  depths 1/2/3 = 390/167/45, avg depth 1.4, max 3.
- Dashboard → **Cascades** page: depth chart, by-route/by-warehouse
  patterns, shipment journey inspector (e.g. stages
  `initial_delay → transfer_disruption → …` with durations).

## 5. Route intelligence (1 minute)

Dashboard → **Routes** page. Factual metrics per route plus transparent
historical risk (NOT a prediction):

- Worst lane: **R2 — 46.6% delay rate, 70.5% historical cascade rate**
  (`cascade_rate = cascades ÷ delayed shipments × 100`).
- `cascade_probability` = empirical P(downstream | initial delay);
  `cascade_recurrence` = weeks with cascades ÷ weeks with delays;
  LOW/MEDIUM/HIGH labels come from `config/route_risk_config.py` and
  always ship beside the raw metrics.

## 6. Prediction / risk (1 minute)

Honest two-layer story — never mix the labels:

- **Historical risk** (§5): what already happened, no model.
- **ML baseline** (Dashboard → **Prediction** page):
  NumPy-only logistic regression on prediction-time features only
  (leakage guard enforced), chronological train/test split.
  Live result: accuracy **0.761** vs majority baseline **0.556**,
  ROC-AUC **0.770**, per-route estimated P(cascade) beside historical
  rates, single-shipment estimator included.
- On thin data (e.g. the LaDe window: 94 delayed, 1 cascade) the same
  page states *"Prediction model unavailable: insufficient validated
  training data."* — no fake predictions, ever.

## 7. Alerts (30 seconds)

Dashboard → **Alerts** page: threshold breaches over observed metrics
(`config/alert_config.py`), each with entity, observed value,
threshold, severity, and JSON evidence.

- Live: **1,277 alerts** (412 critical, 757 warning, 108 info):
  602 cascade, 667 excessive-delay, 8 delay-rate.

## 8. Dashboard (2 minutes)

```bash
streamlit run app/streamlit_app.py
```

Tour: Overview (KPI cards, trend) → Dataset explorer → Delay analysis
→ Routes → Warehouses → Cascades → Prediction → Alerts → Reports.
Sidebar filters (date, route, warehouse, reason, status) apply to every
page; LaDe data shows honest empty states for warehouses/reasons
(LaDe has none — never fabricated); the synthetic demo dataset is
always badged SYNTHETIC.

## 9. Report (1 minute)

```bash
python -m reports.report_generator --run data/processed/runs/run_<id>.json --format markdown
python -m reports.report_generator --run data/processed/runs/run_<id>.json --format html
# outputs: data/processed/runs/report_<id>.md / .html (beside the manifest)
```

12 sections, every figure recomputed from the run's own integrated CSV:
executive summary, run/dataset info, data quality (warnings shown),
KPIs, delays, route intelligence, ML baseline block, cascades,
warehouses, alerts with evidence, interpretation, investigations,
limitations. Synthetic runs are badged; empirical risk is never called
a prediction. Optional delivery (validated only, sends nothing):

```bash
copy .env.example .env   # fill in real SMTP values locally, never commit
python -m reports.email_report --run data/processed/runs/run_<id>.json --dry-run
```

## 10. Business value (30 seconds, say this)

> "We can now name the lanes worth investigating first — R2 and its hub
> W2 repeat cascades at 2–3× the network rate — separate one-off late
> deliveries from propagation patterns, and back every claim with the
> journey, the SQL cross-check, and the report. The ML baseline adds
> estimated cascade probabilities with published validation metrics
> where the data supports it, and says so plainly where it doesn't."

## 11. Limitations (30 seconds, say this — do not skip)

1. Showcase data is **synthetic** (seed 42): realistic shapes for a
   readable demo (~33% delay rate is higher than typical operations),
   not observed performance.
2. Real LaDe coverage is partial by source design: no warehouses,
   transfers, or delay reasons; package cascades need both stages late
   (genuinely rare: 1 of 25,934) so no validated ML model trains there.
3. Cascade sequences are **observed associations in time order, not
   proven cause and effect** — the product says "associated with",
   never "caused by".
4. Alert thresholds are demonstration parameters, not learned from
   production data.
