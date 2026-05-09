from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def plot_equity(equity: pd.DataFrame, out_path: Path, title: str = "Equity Curve") -> None:
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(pd.to_datetime(equity["timestamp"]), equity["equity"], lw=1.2)
    ax.set_title(title)
    ax.set_ylabel("Equity")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_signals(df: pd.DataFrame, trades: pd.DataFrame, out_path: Path, title: str = "Price + Trades") -> None:
    fig, ax = plt.subplots(figsize=(13, 6))
    t = pd.to_datetime(df["timestamp"])
    ax.plot(t, df["close"], color="#444", lw=0.8, label="Close")
    if "ema200" in df.columns:
        ax.plot(t, df["ema200"], color="#1f77b4", lw=0.9, label="EMA200")

    if not trades.empty:
        longs = trades[trades["side"] == "long"]
        shorts = trades[trades["side"] == "short"]
        wins = trades[trades["pnl"] > 0]
        losses = trades[trades["pnl"] <= 0]

        ax.scatter(longs["entry_time"], longs["entry_price"], marker="^", color="#2ca02c", s=28, label="Long entry", zorder=3)
        ax.scatter(shorts["entry_time"], shorts["entry_price"], marker="v", color="#d62728", s=28, label="Short entry", zorder=3)
        ax.scatter(wins["exit_time"], wins["exit_price"], marker="o", facecolors="none", edgecolors="#2ca02c", s=22, label="TP", zorder=3)
        ax.scatter(losses["exit_time"], losses["exit_price"], marker="x", color="#d62728", s=22, label="SL", zorder=3)

    ax.set_title(title)
    ax.set_ylabel("Price (USDT)")
    ax.grid(alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
