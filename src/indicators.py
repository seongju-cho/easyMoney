from __future__ import annotations

import numpy as np
import pandas as pd


def heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """Append HA_open / HA_high / HA_low / HA_close columns."""
    o, h, l, c = df["open"].values, df["high"].values, df["low"].values, df["close"].values
    n = len(df)
    ha_close = (o + h + l + c) / 4.0
    ha_open = np.empty(n)
    ha_open[0] = (o[0] + c[0]) / 2.0
    for i in range(1, n):
        ha_open[i] = (ha_open[i - 1] + ha_close[i - 1]) / 2.0
    ha_high = np.maximum.reduce([h, ha_open, ha_close])
    ha_low = np.minimum.reduce([l, ha_open, ha_close])
    out = df.copy()
    out["ha_open"] = ha_open
    out["ha_high"] = ha_high
    out["ha_low"] = ha_low
    out["ha_close"] = ha_close
    return out


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False, min_periods=length).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = series.diff()
    up = delta.clip(lower=0.0)
    down = (-delta).clip(lower=0.0)
    # Wilder smoothing == EMA with alpha = 1/length
    roll_up = up.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()
    roll_down = down.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()
    rs = roll_up / roll_down.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    out = out.fillna(50.0)
    return out


def stoch_rsi(
    close: pd.Series,
    rsi_length: int = 14,
    stoch_length: int = 14,
    k_smooth: int = 3,
    d_smooth: int = 3,
) -> pd.DataFrame:
    """Standard Stochastic RSI: returns DataFrame with k, d columns (0-100)."""
    r = rsi(close, rsi_length)
    rmin = r.rolling(stoch_length).min()
    rmax = r.rolling(stoch_length).max()
    raw = 100.0 * (r - rmin) / (rmax - rmin).replace(0.0, np.nan)
    k = raw.rolling(k_smooth).mean()
    d = k.rolling(d_smooth).mean()
    return pd.DataFrame({"stoch_k": k, "stoch_d": d})
