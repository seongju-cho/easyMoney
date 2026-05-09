from __future__ import annotations

import pandas as pd

from .indicators import ema, heikin_ashi, stoch_rsi


def build_signals(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Return df augmented with indicators and `signal` column ('long', 'short', or None)
    evaluated at the bar's close. Execution should happen at the next bar's open."""
    df = heikin_ashi(df)
    df["ema200"] = ema(df["close"], cfg["ema_length"])

    sr_cfg = cfg["stoch_rsi"]
    sr = stoch_rsi(
        df["close"],
        rsi_length=sr_cfg["rsi_length"],
        stoch_length=sr_cfg["stoch_length"],
        k_smooth=sr_cfg["k_smooth"],
        d_smooth=sr_cfg["d_smooth"],
    )
    df = pd.concat([df, sr], axis=1)

    k = df["stoch_k"]
    d = df["stoch_d"]
    k_prev = k.shift(1)
    d_prev = d.shift(1)
    golden = (k_prev <= d_prev) & (k > d)
    dead = (k_prev >= d_prev) & (k < d)

    tol = float(cfg.get("wick_tolerance", 1e-9))
    bullish = df["ha_close"] > df["ha_open"]
    bearish = df["ha_close"] < df["ha_open"]
    no_lower_wick = df["ha_low"] >= (df["ha_open"] - tol)
    no_upper_wick = df["ha_high"] <= (df["ha_open"] + tol)

    long_cond = (df["close"] > df["ema200"]) & golden & bullish & no_lower_wick
    short_cond = (df["close"] < df["ema200"]) & dead & bearish & no_upper_wick

    # Zone filter: only accept crosses originating in the extreme zone of Stoch RSI.
    # D (slower line) is used because at the cross K has already moved; D being deep
    # in the zone confirms the cross truly happened in oversold/overbought territory.
    if sr_cfg.get("use_zone_filter", False):
        oversold = float(sr_cfg.get("oversold", 20))
        overbought = float(sr_cfg.get("overbought", 80))
        long_cond = long_cond & (df["stoch_d"] <= oversold)
        short_cond = short_cond & (df["stoch_d"] >= overbought)

    sig = pd.Series(index=df.index, dtype="object")
    sig[long_cond] = "long"
    # short_cond wins if both somehow trigger on the same bar (impossible: golden xor dead)
    sig[short_cond] = "short"
    df["signal"] = sig
    return df
