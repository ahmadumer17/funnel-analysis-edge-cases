# Power BI Integration

> This section documents the end-to-end pipeline connecting the Python
> analysis to an interactive Power BI management report — covering four
> finding-specific pages with drill-through, slicers, and DAX-driven KPI cards.

---

## Architecture

```
events_log_raw.csv
        │
        ▼
export_for_powerbi.py   ← Python (Pandas + funnel_utils logic)
        │
        ├── pbi_fact_events_raw.csv          (1,711 rows + is_duplicate flag)
        ├── pbi_fact_events_clean.csv        (deduplicated events)
        ├── pbi_fact_events_sessionized.csv  (session-labelled events)
        ├── pbi_funnel_naive.csv             (naive funnel counts + rates)
        ├── pbi_funnel_strict.csv            (strict-sequence funnel counts + rates)
        ├── pbi_funnel_comparison.csv        (side-by-side, drives dual-bar chart)
        └── pbi_attribution.csv             (position-based device credits)
                │
                ▼
        Power BI Desktop
                │
                ├── Page 1 — Naive vs Strict Funnel Comparison
                ├── Page 2 — Deduplication: Checkout Volume Integrity
                ├── Page 3 — Sessionization: Cross-Device Drop-off Recovery
                └── Page 4 — Attribution: Mobile Influence
```

The Python layer handles all data engineering (deduplication, sessionization,
strict-sequence logic, position-based attribution).  Power BI consumes clean,
pre-modelled tables and applies DAX measures for KPI cards and derived metrics.

---

## Running the Export

```bash
# From the repo root
pip install pandas numpy
python powerbi_integration/export_for_powerbi.py
```

Source CSVs (`events_log_raw.csv`, `events_deduped.csv`,
`events_sessionized.csv`) are loaded from the repo root.  If any are absent,
the script downloads them from GitHub automatically.

Output is written to `powerbi_integration/output/` — seven CSVs ready
for direct import into Power BI Desktop.

---

## Loading into Power BI Desktop

1. Open Power BI Desktop → **Get Data → Text/CSV**
2. Import all seven files from `powerbi_integration/output/`
3. In Power Query, ensure:
   - `timestamp` columns are parsed as **Date/Time**
   - `is_duplicate` and `converted` columns are parsed as **True/False**
   - `step_order` is parsed as **Whole Number**
4. Close & Apply

No relationships between tables are required — all joins happen in Python
before export, so each table is fully denormalised and self-contained.

---

## DAX Measures

All measures are documented in `powerbi_integration/dax_measures.txt`.

Key measures by page:

| Page | Measure | Purpose |
|------|---------|---------|
| 1 | `Checkout Conversion Inflation (pp)` | Quantifies naive vs strict gap |
| 2 | `Checkout Overcount %` | Shows 49 % overcount from SDK duplicates |
| 3 | `Cross-Device Session Boundaries` | Counts recovered drop-off journeys |
| 4 | `Mobile True Influence (Conversions)` | True mobile-touched conversion count |

To add a measure: **Modeling tab → New Measure**, then paste from the file.

---

## Report Pages

### Page 1 — Funnel Comparison (Naive vs Strict)
Clustered bar chart of funnel steps with Naive and Strict as dual series.
KPI cards surface the 7.1 percentage-point checkout conversion inflation
from orphaned purchase events.  A detail table with conditional formatting
shows per-step conversion rates and drop-off volumes.

### Page 2 — Deduplication: Checkout Volume Integrity
Stacked column chart isolating duplicate checkout events in red against
clean events in green.  KPI cards show the 49 % overcount and duplicate
rate.  A timeline visual plots when duplicate bursts occurred, consistent
with SDK retry or button debounce failure patterns.

### Page 3 — Sessionization: Cross-Device Drop-off Recovery
KPI cards showing total sessions, cross-device session boundaries (34),
and average session duration.  A scatter plot of gap_minutes with a 30-minute
reference line separates genuine drop-offs from device-switch pauses.
A detail table filters to gap > 30 min to isolate recoverable journeys.

### Page 4 — Attribution: Mobile Influence
Side-by-side bar chart comparing Last-Touch, Position-Based, and true
influence credits for each device.  A donut chart shows the credit
distribution across devices for converting users.  KPI cards show
Mobile's true reach: 52.6 % of conversions had a mobile touchpoint,
invisible under standard attribution models.

---

## Parameterized SQL Views (self-serve slicing)

The export script generates structured tables that behave like parameterized
SQL views — the `funnel_model`, `step_order`, and `is_duplicate` columns
allow on-demand slicing by funnel stage, model type, and data quality flag
without re-running the Python pipeline.

This mirrors the approach documented in the CV:
> "Designed parameterized SQL queries and structured views to enable
> on-demand slicing of the dataset by sector, region, and timeline,
> reducing ad-hoc reporting effort and enabling self-serve trend analysis."

---

## File Reference

```
powerbi_integration/
├── export_for_powerbi.py     # Full pipeline: raw CSV → 7 Power BI tables
├── dax_measures.txt          # All DAX measures, grouped by report page
├── report_layout_spec.txt    # Visual-by-visual layout spec for all 4 pages
├── README_POWERBI.md         # This file
└── output/                   # Generated by export_for_powerbi.py
    ├── pbi_fact_events_raw.csv
    ├── pbi_fact_events_clean.csv
    ├── pbi_fact_events_sessionized.csv
    ├── pbi_funnel_naive.csv
    ├── pbi_funnel_strict.csv
    ├── pbi_funnel_comparison.csv
    └── pbi_attribution.csv
```
