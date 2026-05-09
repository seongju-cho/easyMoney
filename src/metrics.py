from __future__ import annotations

import numpy as np
import pandas as pd


def compute_metrics(trades: pd.DataFrame, equity: pd.DataFrame, initial_capital: float, bars_per_year: float) -> dict:
    if equity.empty:
        return {}

    eq = equity["equity"].to_numpy()
    final = float(eq[-1])
    total_return = final / initial_capital - 1.0

    # CAGR
    seconds = (equity["timestamp"].iloc[-1] - equity["timestamp"].iloc[0]) / np.timedelta64(1, "s")
    years = max(seconds / (365.25 * 24 * 3600), 1e-9)
    cagr = (final / initial_capital) ** (1.0 / years) - 1.0 if final > 0 else -1.0

    # Max drawdown
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    max_dd = float(dd.min())

    # Per-bar returns -> Sharpe (annualized)
    rets = pd.Series(eq).pct_change().dropna()
    if rets.std() > 0:
        sharpe = (rets.mean() / rets.std()) * np.sqrt(bars_per_year)
    else:
        sharpe = float("nan")

    out = {
        "initial_capital": initial_capital,
        "final_equity": final,
        "total_return_pct": total_return * 100,
        "cagr_pct": cagr * 100,
        "max_drawdown_pct": max_dd * 100,
        "sharpe_annualized": sharpe,
        "n_trades": int(len(trades)),
    }

    if not trades.empty:
        wins = trades[trades["pnl"] > 0]
        losses = trades[trades["pnl"] <= 0]
        out["win_rate_pct"] = len(wins) / len(trades) * 100
        out["avg_win_pct"] = wins["pnl_pct"].mean() * 100 if not wins.empty else 0.0
        out["avg_loss_pct"] = losses["pnl_pct"].mean() * 100 if not losses.empty else 0.0
        out["best_trade_pct"] = trades["pnl_pct"].max() * 100
        out["worst_trade_pct"] = trades["pnl_pct"].min() * 100
        gp = wins["pnl"].sum()
        gl = -losses["pnl"].sum()
        out["profit_factor"] = (gp / gl) if gl > 0 else float("inf")
        out["avg_bars_held"] = float(trades["bars_held"].mean())
        out["n_long"] = int((trades["side"] == "long").sum())
        out["n_short"] = int((trades["side"] == "short").sum())
        out["n_tp"] = int((trades["exit_reason"] == "tp").sum())
        out["n_sl"] = int((trades["exit_reason"] == "sl").sum())
        # Longest losing streak
        streak = max_streak = 0
        for pnl in trades["pnl"].to_numpy():
            if pnl <= 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        out["max_losing_streak"] = int(max_streak)

    return out


def format_summary(metrics: dict) -> str:
    if not metrics:
        return "No data."
    lines = []
    order = [
        ("initial_capital", "Initial capital", "{:,.2f}"),
        ("final_equity", "Final equity", "{:,.2f}"),
        ("total_return_pct", "Total return", "{:+.2f}%"),
        ("cagr_pct", "CAGR", "{:+.2f}%"),
        ("max_drawdown_pct", "Max drawdown", "{:+.2f}%"),
        ("sharpe_annualized", "Sharpe (annualized)", "{:+.2f}"),
        ("n_trades", "Trades", "{:d}"),
        ("n_long", "  Long", "{:d}"),
        ("n_short", "  Short", "{:d}"),
        ("n_tp", "  TP exits", "{:d}"),
        ("n_sl", "  SL exits", "{:d}"),
        ("win_rate_pct", "Win rate", "{:.2f}%"),
        ("avg_win_pct", "Avg win", "{:+.2f}%"),
        ("avg_loss_pct", "Avg loss", "{:+.2f}%"),
        ("best_trade_pct", "Best trade", "{:+.2f}%"),
        ("worst_trade_pct", "Worst trade", "{:+.2f}%"),
        ("profit_factor", "Profit factor", "{:.2f}"),
        ("avg_bars_held", "Avg bars held", "{:.2f}"),
        ("max_losing_streak", "Max losing streak", "{:d}"),
    ]
    for key, label, fmt in order:
        if key in metrics:
            try:
                val = fmt.format(metrics[key])
            except Exception:
                val = str(metrics[key])
            lines.append(f"{label:<22}: {val}")
    return "\n".join(lines)
