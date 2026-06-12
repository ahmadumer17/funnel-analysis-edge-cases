"""
export_for_powerbi.py
=====================
Runs the full funnel analysis pipeline and exports seven Power BI-ready
CSV tables.  Drop every output file into Power BI Desktop via
Get Data > Text/CSV, then apply the DAX measures in dax_measures.txt.

Output tables
-------------
pbi_fact_events_raw.csv          — raw event log (1 row per event)
pbi_fact_events_clean.csv        — deduplicated event log
pbi_fact_events_sessionized.csv  — sessionized event log
pbi_funnel_naive.csv             — naive funnel step counts + rates
pbi_funnel_strict.csv            — strict-sequence funnel counts + rates
pbi_funnel_comparison.csv        — side-by-side naive vs strict (for dual-bar chart)
pbi_attribution.csv              — position-based device attribution credits

Usage
-----
    python export_for_powerbi.py

Expects the three source CSVs (events_log_raw.csv, events_deduped.csv,
events_sessionized.csv) in the same directory, OR downloads them from
GitHub if they are absent.
"""

import os
import sys
import urllib.request
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))   # repo root

RAW_CSV         = os.path.join(ROOT, "events_log_raw.csv")
DEDUPED_CSV     = os.path.join(ROOT, "events_deduped.csv")
SESSIONIZED_CSV = os.path.join(ROOT, "events_sessionized.csv")

OUT_DIR = os.path.join(HERE, "output")
os.makedirs(OUT_DIR, exist_ok=True)

GITHUB_BASE = (
    "https://raw.githubusercontent.com/"
    "ahmadumer17/funnel-analysis-edge-cases/main/"
)

FUNNEL_STEPS = [
    "home", "product_view", "add_to_cart", "checkout_click", "purchase"
]

# ---------------------------------------------------------------------------
# Helpers — inline reimplementation of funnel_utils so this script is
# self-contained (no import path gymnastics required).
# ---------------------------------------------------------------------------

def _ensure_csv(local_path: str, filename: str) -> None:
    """Download from GitHub if the local file is missing."""
    if not os.path.exists(local_path):
        url = GITHUB_BASE + filename
        print(f"  Downloading {filename} from GitHub …")
        urllib.request.urlretrieve(url, local_path)


def build_naive_funnel(df, funnel_steps):
    results = []
    for step in funnel_steps:
        unique_users = df[df["event"] == step]["user_id"].nunique()
        results.append({"step": step, "unique_users": unique_users})
    result_df = pd.DataFrame(results)
    result_df["prev_users"] = result_df["unique_users"].shift(1)
    result_df["step_conversion_rate"] = (
        result_df["unique_users"] / result_df["prev_users"]
    ).round(4)
    top = result_df.loc[0, "unique_users"]
    result_df["overall_conversion_rate"] = (
        result_df["unique_users"] / top
    ).round(4)
    result_df["drop_off_users"] = (
        result_df["prev_users"] - result_df["unique_users"]
    )
    result_df["step_order"] = range(1, len(funnel_steps) + 1)
    result_df["funnel_model"] = "Naive"
    return result_df.drop(columns=["prev_users"])


def build_strict_funnel(df, funnel_steps):
    first_touch = (
        df[df["event"].isin(funnel_steps)]
        .groupby(["user_id", "event"])["timestamp"]
        .min()
        .reset_index()
        .rename(columns={"timestamp": "first_ts"})
    )
    pivot_df = first_touch.pivot_table(
        index="user_id", columns="event",
        values="first_ts", aggfunc="min"
    )
    pivot_df = pivot_df.reindex(columns=funnel_steps)
    pivot_df.columns.name = None

    strict_funnel = []
    qualifying = pivot_df.copy()
    for i, step in enumerate(funnel_steps):
        if i == 0:
            mask = qualifying[step].notna()
        else:
            prev = funnel_steps[i - 1]
            mask = (
                qualifying[step].notna() &
                (qualifying[step] > qualifying[prev])
            )
        qualifying = qualifying[mask]
        strict_funnel.append({"step": step, "strict_users": len(qualifying)})

    result_df = pd.DataFrame(strict_funnel)
    result_df["prev_users"] = result_df["strict_users"].shift(1)
    result_df["step_conversion_rate"] = (
        result_df["strict_users"] / result_df["prev_users"]
    ).round(4)
    top = result_df.loc[0, "strict_users"]
    result_df["overall_conversion_rate"] = (
        result_df["strict_users"] / top
    ).round(4)
    result_df["drop_off_users"] = (
        result_df["prev_users"] - result_df["strict_users"]
    )
    result_df["step_order"] = range(1, len(funnel_steps) + 1)
    result_df["funnel_model"] = "Strict"
    return result_df.drop(columns=["prev_users"])


def deduplicate_events(df, event_col="event", time_col="timestamp",
                       user_col="user_id", window_seconds=5):
    df_sorted = df.sort_values([user_col, time_col]).reset_index(drop=True)
    df_sorted["_prev_event"] = df_sorted.groupby(user_col)[event_col].shift(1)
    df_sorted["_prev_ts"]    = df_sorted.groupby(user_col)[time_col].shift(1)
    df_sorted["_time_diff"]  = (
        df_sorted[time_col] - df_sorted["_prev_ts"]
    ).dt.total_seconds()
    is_duplicate = (
        (df_sorted[event_col] == df_sorted["_prev_event"]) &
        (df_sorted["_time_diff"] <= window_seconds)
    )
    df_sorted["is_duplicate"] = is_duplicate
    df_clean = df_sorted[~is_duplicate].copy()
    df_clean = df_clean.drop(columns=["_prev_event", "_prev_ts", "_time_diff"])
    return df_clean


def sessionize(df, user_col="user_id", time_col="timestamp",
               timeout_minutes=30):
    df_out = df.sort_values([user_col, time_col]).reset_index(drop=True).copy()
    df_out["_prev_ts"] = df_out.groupby(user_col)[time_col].shift(1)
    df_out["gap_minutes"] = (
        df_out[time_col] - df_out["_prev_ts"]
    ).dt.total_seconds() / 60
    df_out["_is_new_session"] = (
        df_out["gap_minutes"].isna() |
        (df_out["gap_minutes"] > timeout_minutes)
    )
    df_out["_session_num"] = (
        df_out.groupby(user_col)["_is_new_session"].cumsum().astype(int)
    )
    df_out["clean_session_id"] = (
        df_out[user_col] + "_session_" + df_out["_session_num"].astype(str)
    )
    df_out = df_out.drop(columns=["_prev_ts", "_is_new_session", "_session_num"])
    return df_out


def get_device_credits(journey_tuples, converted):
    if not converted:
        return {}
    devices = [d for _, d in journey_tuples]
    unique_devs = list(dict.fromkeys(devices))
    first_device = devices[0]
    last_device  = devices[-1]
    if len(unique_devs) == 1:
        return {first_device: 1.0}
    other = [d for d in unique_devs if d != first_device]
    if first_device == last_device:
        credits = {first_device: 0.80}
        share = 0.20 / len(other)
        for d in other:
            credits[d] = credits.get(d, 0) + share
        return credits
    else:
        middle = [d for d in unique_devs
                  if d != first_device and d != last_device]
        credits = {first_device: 0.40, last_device: 0.40}
        if middle:
            share = 0.20 / len(middle)
            for d in middle:
                credits[d] = credits.get(d, 0) + share
        else:
            credits = {first_device: 0.50, last_device: 0.50}
        return credits


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run():
    print("\n=== Funnel Analysis → Power BI Export ===\n")

    # ------------------------------------------------------------------
    # 1. Load source CSVs (download from GitHub if missing)
    # ------------------------------------------------------------------
    print("[1/6] Loading source data …")
    _ensure_csv(RAW_CSV,         "events_log_raw.csv")
    _ensure_csv(DEDUPED_CSV,     "events_deduped.csv")
    _ensure_csv(SESSIONIZED_CSV, "events_sessionized.csv")

    df_raw  = pd.read_csv(RAW_CSV,         parse_dates=["timestamp"])
    df_ded  = pd.read_csv(DEDUPED_CSV,     parse_dates=["timestamp"])
    df_sess = pd.read_csv(SESSIONIZED_CSV, parse_dates=["timestamp"])

    print(f"  Raw events      : {len(df_raw):,}")
    print(f"  Deduped events  : {len(df_ded):,}")
    print(f"  Sessionized rows: {len(df_sess):,}")

    # ------------------------------------------------------------------
    # 2. Enrich raw events with a duplicate flag (for Power BI filter)
    # ------------------------------------------------------------------
    print("\n[2/6] Enriching raw events …")
    df_raw_enriched = deduplicate_events(df_raw.copy())
    # Restore duplicate rows with a flag column
    df_raw_flag = df_raw.copy()
    df_raw_flag = df_raw_flag.sort_values(["user_id", "timestamp"]).reset_index(drop=True)
    deduped_keys = set(zip(df_raw_enriched["user_id"], df_raw_enriched["timestamp"], df_raw_enriched["event"]))
    df_raw_flag["is_duplicate"] = ~df_raw_flag.apply(
        lambda r: (r["user_id"], r["timestamp"], r["event"]) in deduped_keys, axis=1
    )

    # ------------------------------------------------------------------
    # 3. Sessionize clean events
    # ------------------------------------------------------------------
    print("[3/6] Sessionizing clean events …")
    df_sess_computed = sessionize(df_raw_enriched.drop(columns=["is_duplicate"], errors="ignore"))

    # ------------------------------------------------------------------
    # 4. Build funnel tables
    # ------------------------------------------------------------------
    print("[4/6] Building funnel comparison tables …")
    naive_df  = build_naive_funnel(df_raw,          FUNNEL_STEPS)
    strict_df = build_strict_funnel(df_raw_enriched, FUNNEL_STEPS)

    # Rename user count columns to a common name for the comparison table
    naive_renamed  = naive_df.rename(columns={"unique_users": "users"})
    strict_renamed = strict_df.rename(columns={"strict_users": "users"})
    comparison_df  = pd.concat([naive_renamed, strict_renamed], ignore_index=True)
    comparison_df["step_label"] = comparison_df["step"].str.replace("_", " ").str.title()

    # ------------------------------------------------------------------
    # 5. Attribution table
    # ------------------------------------------------------------------
    print("[5/6] Computing position-based attribution …")
    if "device" in df_sess_computed.columns:
        device_col = "device"
    elif "device_type" in df_sess_computed.columns:
        device_col = "device_type"
    else:
        device_col = None

    attribution_rows = []
    if device_col:
        converted_users = set(
            df_sess_computed[df_sess_computed["event"] == "purchase"]["user_id"]
        )
        for uid, grp in df_sess_computed.sort_values("timestamp").groupby("user_id"):
            journey = list(zip(grp["event"], grp[device_col]))
            converted = uid in converted_users
            credits = get_device_credits(journey, converted)
            for device, credit in credits.items():
                attribution_rows.append({
                    "user_id"    : uid,
                    "device"     : device,
                    "credit"     : round(credit, 4),
                    "converted"  : converted
                })
    else:
        print("  WARNING: no 'device' column found — attribution table will be empty.")

    attribution_df = pd.DataFrame(attribution_rows) if attribution_rows else pd.DataFrame(
        columns=["user_id", "device", "credit", "converted"]
    )

    # ------------------------------------------------------------------
    # 6. Export all tables
    # ------------------------------------------------------------------
    print("\n[6/6] Writing Power BI CSVs to", OUT_DIR)
    exports = {
        "pbi_fact_events_raw.csv"         : df_raw_flag,
        "pbi_fact_events_clean.csv"       : df_raw_enriched,
        "pbi_fact_events_sessionized.csv" : df_sess_computed,
        "pbi_funnel_naive.csv"            : naive_df,
        "pbi_funnel_strict.csv"           : strict_df,
        "pbi_funnel_comparison.csv"       : comparison_df,
        "pbi_attribution.csv"             : attribution_df,
    }
    for filename, df in exports.items():
        path = os.path.join(OUT_DIR, filename)
        df.to_csv(path, index=False)
        print(f"  ✓ {filename}  ({len(df):,} rows)")

    print("\n=== Export complete ===")
    print(f"Load all 7 CSVs from  {OUT_DIR}  into Power BI Desktop.")
    print("Then apply the DAX measures in  powerbi_integration/dax_measures.txt\n")


if __name__ == "__main__":
    run()
