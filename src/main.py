from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from .backtester import run_backtest
from .data_loader import load_ohlcv
from .metrics import compute_metrics, format_summary
from .plotter import plot_equity, plot_signals
from .strategy import build_signals


BARS_PER_YEAR = {
    "1m": 60 * 24 * 365,
    "5m": 12 * 24 * 365,
    "15m": 4 * 24 * 365,
    "1h": 24 * 365,
    "4h": 6 * 365,
    "1d": 365,
}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--refresh", action="store_true", help="Re-download data ignoring cache")
    p.add_argument("--results", default="results")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text())

    print(f"Loading {cfg['symbol']} {cfg['timeframe']} {cfg['start']} -> {cfg['end']}")
    df = load_ohlcv(cfg["symbol"], cfg["timeframe"], cfg["start"], cfg["end"], refresh=args.refresh)
    print(f"  {len(df)} bars loaded")

    print("Building signals...")
    df = build_signals(df, cfg)
    n_long = int((df["signal"] == "long").sum())
    n_short = int((df["signal"] == "short").sum())
    print(f"  Long signals: {n_long}, Short signals: {n_short}")

    print("Running backtest...")
    trades, equity = run_backtest(df, cfg)
    print(f"  {len(trades)} trades")

    bars_per_year = BARS_PER_YEAR.get(cfg["timeframe"], 24 * 365)
    metrics = compute_metrics(trades, equity, float(cfg["initial_capital"]), bars_per_year)

    results_dir = Path(args.results)
    results_dir.mkdir(parents=True, exist_ok=True)

    trades_path = results_dir / "trades.csv"
    equity_path = results_dir / "equity.csv"
    summary_path = results_dir / "summary.txt"
    eq_png = results_dir / "equity_curve.png"
    sig_png = results_dir / "signals.png"

    trades.to_csv(trades_path, index=False)
    equity.to_csv(equity_path, index=False)

    summary = format_summary(metrics)
    summary_header = (
        f"Symbol         : {cfg['symbol']}\n"
        f"Timeframe      : {cfg['timeframe']}\n"
        f"Period         : {cfg['start']} -> {cfg['end']}\n"
        f"SL / TP        : -{cfg['sl_pct']*100:.2f}% / +{cfg['tp_pct']*100:.2f}%\n"
        f"Fee / Slippage : {cfg['fee_pct']*100:.3f}% / {cfg['slippage_pct']*100:.3f}%\n"
        f"Same-bar       : {cfg.get('same_bar_priority','SL')} priority\n"
        + ("-" * 48) + "\n"
    )
    full = summary_header + summary + "\n"
    summary_path.write_text(full)
    print("\n" + full)

    plot_equity(equity, eq_png, title=f"{cfg['symbol']} {cfg['timeframe']} Equity")
    plot_signals(df, trades, sig_png, title=f"{cfg['symbol']} {cfg['timeframe']} Trades")

    print(f"Results saved to: {results_dir.resolve()}")


if __name__ == "__main__":
    main()
