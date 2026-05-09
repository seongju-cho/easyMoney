from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

BINANCE_HOSTS = [
    "https://api.binance.com",
    "https://data-api.binance.vision",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
]

INTERVAL_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
    "8h": 28_800_000, "12h": 43_200_000, "1d": 86_400_000,
}


def _to_ms(date_str: str) -> int:
    dt = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _fetch_chunk(symbol: str, interval: str, start_ms: int, end_ms: int) -> list:
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": 1000,
    }
    last_err = None
    for host in BINANCE_HOSTS:
        url = f"{host}/api/v3/klines"
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, timeout=20)
                if r.status_code == 200:
                    return r.json()
                last_err = f"{host} -> HTTP {r.status_code}: {r.text[:200]}"
            except Exception as e:
                last_err = f"{host} -> {type(e).__name__}: {e}"
            time.sleep(1.5 ** attempt)
    raise RuntimeError(f"All Binance hosts failed. Last error: {last_err}")


def fetch_klines(symbol: str, interval: str, start: str, end: str) -> pd.DataFrame:
    if interval not in INTERVAL_MS:
        raise ValueError(f"Unsupported interval: {interval}")
    step = INTERVAL_MS[interval] * 1000  # 1000 candles per request
    start_ms = _to_ms(start)
    end_ms = _to_ms(end)

    rows = []
    cursor = start_ms
    while cursor < end_ms:
        chunk_end = min(cursor + step, end_ms)
        chunk = _fetch_chunk(symbol, interval, cursor, chunk_end)
        if not chunk:
            cursor = chunk_end
            continue
        rows.extend(chunk)
        last_open = chunk[-1][0]
        # advance one bar past the last received open
        next_cursor = last_open + INTERVAL_MS[interval]
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        time.sleep(0.25)  # gentle on rate limits

    if not rows:
        raise RuntimeError("No data returned from Binance")

    df = pd.DataFrame(
        rows,
        columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore",
        ],
    )
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c])
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def load_ohlcv(
    symbol: str,
    interval: str,
    start: str,
    end: str,
    cache_dir: str | Path = "data",
    refresh: bool = False,
) -> pd.DataFrame:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{symbol}_{interval}_{start}_{end}.parquet"

    if cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path)

    df = fetch_klines(symbol, interval, start, end)
    try:
        df.to_parquet(cache_path, index=False)
    except Exception:
        df.to_csv(cache_path.with_suffix(".csv"), index=False)
    return df
