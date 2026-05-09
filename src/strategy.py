from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import atr, ema, heikin_ashi, stoch_rsi


def _direction_filter(sig: pd.Series, mode: str) -> pd.Series:
    mode = (mode or "both").lower()
    if mode == "long_only":
        sig = sig.where(sig != "short", other=None)
    elif mode == "short_only":
        sig = sig.where(sig != "long", other=None)
    return sig


# ---------------------------------------------------------------- ha_stoch_rsi
def gen_ha_stoch_rsi(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Heikin-Ashi candle + 200 EMA trend + Stoch RSI cross (original strategy)."""
    df = heikin_ashi(df)
    df["ema200"] = ema(df["close"], cfg["ema_length"])
    df["atr"] = atr(df, int(cfg.get("atr_length", 14)))

    sr_cfg = cfg["stoch_rsi"]
    sr = stoch_rsi(df["close"],
                   rsi_length=sr_cfg["rsi_length"], stoch_length=sr_cfg["stoch_length"],
                   k_smooth=sr_cfg["k_smooth"], d_smooth=sr_cfg["d_smooth"])
    df = pd.concat([df, sr], axis=1)

    k, d = df["stoch_k"], df["stoch_d"]
    golden = (k.shift(1) <= d.shift(1)) & (k > d)
    dead = (k.shift(1) >= d.shift(1)) & (k < d)

    tol = float(cfg.get("wick_tolerance", 1e-9))
    bullish = df["ha_close"] > df["ha_open"]
    bearish = df["ha_close"] < df["ha_open"]
    no_lower_wick = df["ha_low"] >= (df["ha_open"] - tol)
    no_upper_wick = df["ha_high"] <= (df["ha_open"] + tol)

    long_cond = (df["close"] > df["ema200"]) & golden & bullish & no_lower_wick
    short_cond = (df["close"] < df["ema200"]) & dead & bearish & no_upper_wick

    if sr_cfg.get("use_zone_filter", False):
        oversold = float(sr_cfg.get("oversold", 20))
        overbought = float(sr_cfg.get("overbought", 80))
        long_cond &= (df["stoch_d"] <= oversold)
        short_cond &= (df["stoch_d"] >= overbought)

    sig = pd.Series(index=df.index, dtype="object")
    sig[long_cond] = "long"
    sig[short_cond] = "short"
    df["signal"] = _direction_filter(sig, cfg.get("direction_mode", "both"))
    return df


# ---------------------------------------------------------------- donchian_breakout
def gen_donchian_breakout(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Trend-following: close breaks N-bar high (long) / low (short).
    Optional 200 EMA trend filter.
    """
    df = df.copy()
    df["ema200"] = ema(df["close"], cfg["ema_length"])
    df["atr"] = atr(df, int(cfg.get("atr_length", 14)))

    n = int(cfg.get("donchian", {}).get("length", 20))
    # rolling max of last N bars EXCLUDING current bar (use shift(1))
    upper = df["high"].rolling(n).max().shift(1)
    lower = df["low"].rolling(n).min().shift(1)
    df["donchian_upper"] = upper
    df["donchian_lower"] = lower

    # Breakout: today's close > prior N-bar high
    long_cond = df["close"] > upper
    short_cond = df["close"] < lower

    if cfg.get("donchian", {}).get("use_ema_filter", True):
        long_cond &= (df["close"] > df["ema200"])
        short_cond &= (df["close"] < df["ema200"])

    # Edge-trigger: only on the bar the condition flips on
    long_trig = long_cond & ~long_cond.shift(1, fill_value=False)
    short_trig = short_cond & ~short_cond.shift(1, fill_value=False)

    sig = pd.Series(index=df.index, dtype="object")
    sig[long_trig] = "long"
    sig[short_trig] = "short"
    df["signal"] = _direction_filter(sig, cfg.get("direction_mode", "both"))
    return df


# ---------------------------------------------------------------- bb_reversion
def gen_bb_reversion(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Mean-reversion: pierce a Bollinger Band, close back inside (rejection)."""
    df = df.copy()
    df["ema200"] = ema(df["close"], cfg["ema_length"])
    df["atr"] = atr(df, int(cfg.get("atr_length", 14)))

    bb = cfg.get("bb", {})
    length = int(bb.get("length", 20))
    nstd = float(bb.get("std", 2.0))
    use_ema = bool(bb.get("use_ema_filter", False))

    mid = df["close"].rolling(length).mean()
    sd = df["close"].rolling(length).std(ddof=0)
    upper = mid + nstd * sd
    lower = mid - nstd * sd
    df["bb_mid"] = mid
    df["bb_upper"] = upper
    df["bb_lower"] = lower

    # Long: low pierced below lower band but close back above lower band
    long_cond = (df["low"] < lower) & (df["close"] > lower)
    # Short: high pierced above upper band but close back below upper band
    short_cond = (df["high"] > upper) & (df["close"] < upper)

    if use_ema:
        long_cond &= (df["close"] > df["ema200"])
        short_cond &= (df["close"] < df["ema200"])

    sig = pd.Series(index=df.index, dtype="object")
    sig[long_cond] = "long"
    sig[short_cond] = "short"
    df["signal"] = _direction_filter(sig, cfg.get("direction_mode", "both"))
    return df


SIGNAL_GENERATORS = {
    "ha_stoch_rsi": gen_ha_stoch_rsi,
    "donchian_breakout": gen_donchian_breakout,
    "bb_reversion": gen_bb_reversion,
}


def build_signals(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    name = str(cfg.get("strategy_name", "ha_stoch_rsi"))
    gen = SIGNAL_GENERATORS.get(name)
    if gen is None:
        raise ValueError(f"Unknown strategy_name: {name}. Options: {list(SIGNAL_GENERATORS)}")
    return gen(df, cfg)
