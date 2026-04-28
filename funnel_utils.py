import pandas as pd
import numpy as np


def build_naive_funnel(df, funnel_steps):
    """
    Naive funnel — unique users per step, no sequence enforcement.
    Warning: intentionally overcounts. Use to demonstrate inflation only.
    """
    results = []
    for step in funnel_steps:
        unique_users = df[df["event"] == step]["user_id"].nunique()
        results.append({"step": step, "unique_users": unique_users})
    result_df = pd.DataFrame(results)
    result_df["prev_users"] = result_df["unique_users"].shift(1)
    result_df["conversion_rate"] = (
        result_df["unique_users"] / result_df["prev_users"]
    ).round(3)
    top = result_df.loc[0, "unique_users"]
    result_df["overall_conv"] = (result_df["unique_users"] / top).round(3)
    return result_df


def build_strict_funnel(df, funnel_steps):
    """
    Strict sequence funnel — enforces chronological step order.
    User must complete step N before step N+1 to qualify.
    """
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
    pivot_df = pivot_df[funnel_steps]
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
    result_df["conversion_rate"] = (
        result_df["strict_users"] / result_df["prev_users"]
    ).round(3)
    top = result_df.loc[0, "strict_users"]
    result_df["overall_conv"] = (result_df["strict_users"] / top).round(3)
    return result_df


def deduplicate_events(df, event_col="event", time_col="timestamp",
                       user_col="user_id", window_seconds=5):
    """
    Remove duplicate events fired within a short time window.
    Targets SDK retries, button double-taps, race conditions.
    """
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
    df_clean = df_sorted[~is_duplicate].copy()
    df_clean = df_clean.drop(columns=["_prev_event", "_prev_ts", "_time_diff"])
    return df_clean


def sessionize(df, user_col="user_id", time_col="timestamp",
               timeout_minutes=30):
    """
    Assign session labels using inactivity timeout.
    New session starts when user is idle beyond timeout_minutes.
    """
    df_out = df.sort_values([user_col, time_col]).reset_index(drop=True).copy()
    df_out["_prev_ts"]        = df_out.groupby(user_col)[time_col].shift(1)
    df_out["gap_minutes"]     = (
        df_out[time_col] - df_out["_prev_ts"]
    ).dt.total_seconds() / 60
    df_out["_is_new_session"] = (
        df_out["gap_minutes"].isna() |
        (df_out["gap_minutes"] > timeout_minutes)
    )
    df_out["_session_num"]    = (
        df_out.groupby(user_col)["_is_new_session"].cumsum().astype(int)
    )
    df_out["clean_session_id"] = (
        df_out[user_col] + "_session_" + df_out["_session_num"].astype(str)
    )
    df_out = df_out.drop(
        columns=["_prev_ts", "_is_new_session", "_session_num"]
    )
    return df_out


def get_device_credits(journey_tuples, converted):
    """
    Position-based attribution for cross-device journeys.
    Primary device (first=last): 80% credit.
    Mid-funnel device:           20% credit.
    True start-to-end switch:    40% first, 20% middle, 40% last.
    """
    if not converted:
        return {}
    devices      = [d for _, d in journey_tuples]
    unique_devs  = list(dict.fromkeys(devices))
    first_device = devices[0]
    last_device  = devices[-1]
    if len(unique_devs) == 1:
        return {first_device: 1.0}
    other = [d for d in unique_devs if d != first_device]
    if first_device == last_device:
        credits = {first_device: 0.80}
        share   = 0.20 / len(other)
        for d in other:
            credits[d] = credits.get(d, 0) + share
        return credits
    else:
        middle  = [d for d in unique_devs
                   if d != first_device and d != last_device]
        credits = {first_device: 0.40, last_device: 0.40}
        if middle:
            share = 0.20 / len(middle)
            for d in middle:
                credits[d] = credits.get(d, 0) + share
        else:
            credits = {first_device: 0.50, last_device: 0.50}
        return credits
