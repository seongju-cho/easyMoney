"""Ablation runner: compare strategy variants side-by-side."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path

import pandas as pd
import yaml
from tabulate import tabulate

from .backtester import run_backtest
from .data_loader import load_ohlcv
from .metrics import compute_metrics
from .plotter import plot_equity
from .strategy import build_signals


BARS_PER_YEAR = {"1m": 525_600, "5m": 105_120, "15m": 35_040, "1h": 8_760, "4h": 2_190, "1d": 365}


def variants(base: dict) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []

    def derive(name: str, **overrides) -> tuple[str, dict]:
        c = copy.deepcopy(base)
        # also force risk_pct sizing for fair apples-to-apples comparison
        c["sizing_mode"] = "risk_pct"
        for k, v in overrides.items():
            if "." in k:
                a, b = k.split(".", 1)
                c[a][b] = v
            else:
                c[k] = v
        return name, c

    mode = (base.get("compare_mode") or "ablation").lower()
    if mode == "strategies":
        out.append(derive("ha_stoch_rsi (zone filter on)", strategy_name="ha_stoch_rsi"))
        out.append(derive("donchian_breakout (20)", strategy_name="donchian_breakout"))
        out.append(derive("bb_reversion (20, 2.0)", strategy_name="bb_reversion"))
        return out

    # default: parameter ablation on the current strategy
    out.append(derive("0_baseline (zone filter)"))
    out.append(derive("1_long_only", direction_mode="long_only"))
    out.append(derive("2_atr_stops", stop_mode="atr"))
    out.append(derive("3_opp_exit", exit_on_opposite_signal=True))
    out.append(derive("4_all_three",
                      direction_mode="long_only",
                      stop_mode="atr",
                      exit_on_opposite_signal=True))
    return out


def run_one(name: str, cfg: dict, df_raw: pd.DataFrame, out_dir: Path) -> dict:
    df = build_signals(df_raw.copy(), cfg)
    trades, equity = run_backtest(df, cfg)
    bpy = BARS_PER_YEAR.get(cfg["timeframe"], 8760)
    m = compute_metrics(trades, equity, float(cfg["initial_capital"]), bpy)

    sub = out_dir / name
    sub.mkdir(parents=True, exist_ok=True)
    trades.to_csv(sub / "trades.csv", index=False)
    equity.to_csv(sub / "equity.csv", index=False)
    plot_equity(equity, sub / "equity_curve.png", title=name)

    return {
        "variant": name,
        "trades": m.get("n_trades", 0),
        "L/S": f"{m.get('n_long', 0)}/{m.get('n_short', 0)}",
        "WR%": round(m.get("win_rate_pct", 0), 1),
        "PF": round(m.get("profit_factor", 0), 2) if m.get("profit_factor") not in (None, float("inf")) else "inf",
        "Ret%": round(m.get("total_return_pct", 0), 2),
        "CAGR%": round(m.get("cagr_pct", 0), 2),
        "MDD%": round(m.get("max_drawdown_pct", 0), 2),
        "Sharpe": round(m.get("sharpe_annualized", 0), 2),
        "AvgWin%": round(m.get("avg_win_pct", 0), 2),
        "AvgLoss%": round(m.get("avg_loss_pct", 0), 2),
        "AvgBars": round(m.get("avg_bars_held", 0), 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--results", default="results_compare")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--mode", choices=["ablation", "strategies"], default="ablation",
                    help="ablation: vary one knob at a time on current strategy. "
                         "strategies: compare different strategy_name values.")
    args = ap.parse_args()

    base = yaml.safe_load(Path(args.config).read_text())
    base["compare_mode"] = args.mode
    print(f"Loading {base['symbol']} {base['timeframe']} {base['start']} -> {base['end']}")
    df_raw = load_ohlcv(base["symbol"], base["timeframe"], base["start"], base["end"], refresh=args.refresh)
    print(f"  {len(df_raw)} bars")

    out_dir = Path(args.results)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for name, cfg in variants(base):
        print(f"\n>>> {name}")
        rows.append(run_one(name, cfg, df_raw, out_dir))

    table = tabulate(rows, headers="keys", tablefmt="github", floatfmt=".2f")
    print("\n" + "=" * 80)
    print("ABLATION RESULTS (sizing_mode=risk_pct, risk per trade ~= 1% equity)")
    print("=" * 80)
    print(table)
    (out_dir / "summary.md").write_text(
        "# Ablation Results\n\nAll variants use `sizing_mode=risk_pct` (1% risk per trade) for fair comparison.\n\n"
        + table + "\n"
    )
    print(f"\nSaved to: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
