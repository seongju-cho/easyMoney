"""MFE / MAE analysis for the current strategy's signals.

For each entry signal:
  - Look at the next `lookahead_bars` bars
  - Compute MFE (max favorable excursion) and MAE (max adverse excursion)
    in % of entry price (entry = next bar's open after the signal)
  - Walk forward bar by bar to determine, for each (SL%, TP%) combo, whether
    SL or TP would have fired first (intrabar; same-bar -> SL priority)

Outputs:
  - excursions.csv: per-signal MFE/MAE + final return at lookahead horizon
  - excursion_stats.txt: median MFE/MAE for win/loss separation
  - sltp_grid.csv: WR, PF, expectancy for each (SL, TP) combo
  - sltp_grid.png: heatmap of expectancy
  - excursion_hist.png: histograms / scatter
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from tabulate import tabulate

from .data_loader import load_ohlcv
from .strategy import build_signals


def per_signal_walk(
    o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray,
    sig_idx: int, side: str, lookahead: int, slip: float,
) -> dict:
    """Return per-signal stats: entry price, MFE/MAE %, final return %, and
    a list of (bar_offset, high_excursion, low_excursion) for grid sim."""
    n = len(o)
    if sig_idx + 1 >= n:
        return None
    entry_idx = sig_idx + 1
    entry = o[entry_idx] * (1.0 + slip if side == "long" else 1.0 - slip)
    end_idx = min(entry_idx + lookahead, n - 1)

    mfe = 0.0
    mae = 0.0
    bar_paths = []  # (offset, fav_pct, adv_pct) per bar
    for j in range(entry_idx, end_idx + 1):
        if side == "long":
            fav = (h[j] - entry) / entry
            adv = (entry - l[j]) / entry
        else:
            fav = (entry - l[j]) / entry
            adv = (h[j] - entry) / entry
        mfe = max(mfe, fav)
        mae = max(mae, adv)
        bar_paths.append((j - entry_idx, fav, adv))

    final = (c[end_idx] - entry) / entry if side == "long" else (entry - c[end_idx]) / entry

    return {
        "side": side, "sig_idx": sig_idx, "entry_idx": entry_idx,
        "entry": entry, "mfe_pct": mfe * 100, "mae_pct": mae * 100,
        "final_pct": final * 100, "bar_paths": bar_paths,
        "lookahead_used": end_idx - entry_idx,
    }


def simulate_sltp(bar_paths: list, sl_pct: float, tp_pct: float, same_bar: str = "SL") -> tuple[str, float]:
    """Walk forward; return (outcome, pnl_pct).
    outcome in {'tp', 'sl', 'open'}. pnl_pct excludes fees/slippage; caller adjusts."""
    for offset, fav, adv in bar_paths:
        hit_tp = fav >= tp_pct
        hit_sl = adv >= sl_pct
        if hit_tp and hit_sl:
            if same_bar == "SL":
                return "sl", -sl_pct
            return "tp", tp_pct
        if hit_tp:
            return "tp", tp_pct
        if hit_sl:
            return "sl", -sl_pct
    return "open", 0.0


def analyze(cfg: dict, lookahead: int, sl_grid: list, tp_grid: list, fee: float, slip: float, out_dir: Path) -> None:
    df_raw = load_ohlcv(cfg["symbol"], cfg["timeframe"], cfg["start"], cfg["end"])
    df = build_signals(df_raw, cfg)

    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    sig = df["signal"].to_numpy()

    sigs = []
    for i in range(len(df)):
        s = sig[i]
        if s in ("long", "short"):
            res = per_signal_walk(o, h, l, c, i, s, lookahead, slip)
            if res is not None:
                sigs.append(res)
    print(f"  Signals analyzed: {len(sigs)}")
    if not sigs:
        print("  No signals to analyze. Loosen filters in config.yaml first.")
        return

    # ----- Per-signal table -----
    df_sig = pd.DataFrame([{k: v for k, v in s.items() if k != "bar_paths"} for s in sigs])
    df_sig.to_csv(out_dir / "excursions.csv", index=False)

    # ----- Excursion stats -----
    longs = df_sig[df_sig.side == "long"]
    shorts = df_sig[df_sig.side == "short"]

    def pack(g: pd.DataFrame) -> dict:
        if g.empty:
            return {"n": 0}
        return {
            "n": len(g),
            "median_MFE%": round(g.mfe_pct.median(), 2),
            "median_MAE%": round(g.mae_pct.median(), 2),
            "mean_MFE%": round(g.mfe_pct.mean(), 2),
            "mean_MAE%": round(g.mae_pct.mean(), 2),
            "p25_MFE%": round(g.mfe_pct.quantile(0.25), 2),
            "p75_MFE%": round(g.mfe_pct.quantile(0.75), 2),
            "p75_MAE%": round(g.mae_pct.quantile(0.75), 2),
            "median_final%": round(g.final_pct.median(), 2),
            "%pos_final": round((g.final_pct > 0).mean() * 100, 1),
        }

    stats_rows = []
    for name, g in [("ALL", df_sig), ("long", longs), ("short", shorts)]:
        row = {"group": name}
        row.update(pack(g))
        stats_rows.append(row)
    stats_table = tabulate(stats_rows, headers="keys", tablefmt="github")
    print("\n=== Excursion stats (lookahead = {} bars) ===".format(lookahead))
    print(stats_table)

    # ----- SL/TP grid sweep -----
    same_bar = str(cfg.get("same_bar_priority", "SL")).upper()
    grid_rows = []
    fee_rt = 2 * fee  # round-trip fee % approximation (entry + exit notional)
    slip_adverse = slip  # additional adverse on entry; SL adds another slip
    for sl in sl_grid:
        for tp in tp_grid:
            wins = losses = open_ = 0
            pnls = []
            for s in sigs:
                outcome, pnl = simulate_sltp(s["bar_paths"], sl / 100.0, tp / 100.0, same_bar=same_bar)
                # Apply fees + slippage approximately:
                # entry slippage already in entry price; exit slippage applied to SL only.
                # Subtract round-trip fees and one extra slip for SL fills.
                if outcome == "tp":
                    pnl_net = pnl - fee_rt - slip_adverse  # only entry slip already counted above? we approximate
                    wins += 1
                elif outcome == "sl":
                    pnl_net = pnl - fee_rt - slip_adverse  # adverse on stop fill
                    losses += 1
                else:
                    pnl_net = pnl - fee_rt
                    open_ += 1
                pnls.append(pnl_net)
            arr = np.array(pnls)
            n = len(arr)
            wr = (arr > 0).mean() * 100
            gp = arr[arr > 0].sum()
            gl = -arr[arr < 0].sum()
            pf = (gp / gl) if gl > 0 else float("inf")
            exp = arr.mean() * 100  # avg expectancy in %
            grid_rows.append({
                "SL%": sl, "TP%": tp, "n": n,
                "WR%": round(wr, 1), "PF": round(pf, 2) if pf != float("inf") else float("inf"),
                "Exp%/trade": round(exp, 3),
                "TP_hits": wins, "SL_hits": losses, "Open": open_,
            })
    grid_df = pd.DataFrame(grid_rows)
    grid_df.to_csv(out_dir / "sltp_grid.csv", index=False)

    # Top 10 by expectancy
    top = grid_df.sort_values("Exp%/trade", ascending=False).head(10)
    print("\n=== Top 10 (SL, TP) combos by expectancy ===")
    print(tabulate(top, headers="keys", tablefmt="github", floatfmt=".2f", showindex=False))

    print("\n=== Current strategy SL=1.5%, TP=3.0% reference ===")
    ref = grid_df[(grid_df["SL%"] == 1.5) & (grid_df["TP%"] == 3.0)]
    if not ref.empty:
        print(tabulate(ref, headers="keys", tablefmt="github", floatfmt=".2f", showindex=False))

    # ----- Plots -----
    # Heatmap of expectancy
    pivot_exp = grid_df.pivot(index="SL%", columns="TP%", values="Exp%/trade")
    fig, ax = plt.subplots(figsize=(9, 6))
    im = ax.imshow(pivot_exp.values, aspect="auto", cmap="RdYlGn",
                   extent=[min(tp_grid) - 0.25, max(tp_grid) + 0.25,
                           max(sl_grid) + 0.25, min(sl_grid) - 0.25])
    ax.set_xticks(tp_grid); ax.set_yticks(sl_grid)
    ax.set_xlabel("TP %"); ax.set_ylabel("SL %")
    ax.set_title("Expectancy %/trade by (SL, TP)")
    for i, sl in enumerate(sl_grid):
        for j, tp in enumerate(tp_grid):
            v = pivot_exp.iloc[i, j]
            ax.text(tp, sl, f"{v:+.2f}", ha="center", va="center", fontsize=7,
                    color="black" if abs(v) < 0.5 else "white")
    plt.colorbar(im, ax=ax, label="Exp %/trade")
    fig.tight_layout()
    fig.savefig(out_dir / "sltp_heatmap.png", dpi=120)
    plt.close(fig)

    # Excursion scatter MFE vs MAE
    fig, ax = plt.subplots(figsize=(9, 6))
    win_mask = df_sig.final_pct > 0
    ax.scatter(df_sig.loc[~win_mask, "mae_pct"], df_sig.loc[~win_mask, "mfe_pct"],
               c="#d62728", s=18, alpha=0.6, label="final < 0")
    ax.scatter(df_sig.loc[win_mask, "mae_pct"], df_sig.loc[win_mask, "mfe_pct"],
               c="#2ca02c", s=18, alpha=0.6, label="final > 0")
    ax.axvline(1.5, ls="--", color="#888", lw=0.8)
    ax.axhline(3.0, ls="--", color="#888", lw=0.8)
    ax.set_xlabel("MAE % (max adverse)")
    ax.set_ylabel("MFE % (max favorable)")
    ax.set_title("MFE vs MAE per signal (dashed = current SL=1.5, TP=3.0)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "mfe_mae_scatter.png", dpi=120)
    plt.close(fig)

    # Histograms
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].hist(df_sig.mfe_pct, bins=30, color="#2ca02c", alpha=0.7)
    axes[0].axvline(3.0, ls="--", color="k"); axes[0].set_title(f"MFE distribution (n={len(df_sig)})")
    axes[0].set_xlabel("MFE %")
    axes[1].hist(df_sig.mae_pct, bins=30, color="#d62728", alpha=0.7)
    axes[1].axvline(1.5, ls="--", color="k"); axes[1].set_title("MAE distribution")
    axes[1].set_xlabel("MAE %")
    fig.tight_layout()
    fig.savefig(out_dir / "excursion_hist.png", dpi=120)
    plt.close(fig)

    (out_dir / "excursion_stats.txt").write_text(stats_table + "\n")
    print(f"\nSaved to: {out_dir.resolve()}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--lookahead", type=int, default=72,
                    help="Bars to look ahead per signal (default 72 = 3 days on 1H)")
    ap.add_argument("--results", default="results_analyze")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    out_dir = Path(args.results)
    out_dir.mkdir(parents=True, exist_ok=True)

    sl_grid = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
    tp_grid = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]

    analyze(cfg, args.lookahead, sl_grid, tp_grid,
            float(cfg["fee_pct"]), float(cfg["slippage_pct"]), out_dir)


if __name__ == "__main__":
    main()
