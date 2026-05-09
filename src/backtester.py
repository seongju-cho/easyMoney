from __future__ import annotations

from dataclasses import dataclass, asdict

import pandas as pd


@dataclass
class Trade:
    side: str
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    exit_reason: str   # 'tp', 'sl'
    qty: float
    pnl: float
    pnl_pct: float
    bars_held: int


def run_backtest(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Event-driven backtest.

    Rules:
      - Signal evaluated on bar t close, executed at bar t+1 open.
      - SL/TP intrabar by high/low. If both hit in one bar, `same_bar_priority` decides.
      - Slippage: adverse on entry (market) and on SL fill (stop-market).
        TP is treated as a limit fill at exact tp_price (no slippage).
      - One position at a time; signals during a position are ignored.
      - Fees applied to entry and exit notional separately.

    Equity model: track total account equity as a single number. On entry we
    only debit the entry fee (notional is "invested", not deducted). On exit
    we credit gross PnL and debit the exit fee.
    """
    equity = float(cfg["initial_capital"])
    fee = float(cfg["fee_pct"])
    slip = float(cfg["slippage_pct"])
    sl_pct = float(cfg["sl_pct"])
    tp_pct = float(cfg["tp_pct"])
    pos_pct = float(cfg["position_pct"])
    same_bar = str(cfg.get("same_bar_priority", "SL")).upper()

    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    ts = df["timestamp"].to_numpy()
    sig = df["signal"].to_numpy()

    trades: list[Trade] = []
    equity_curve_ts = []
    equity_curve_eq = []

    in_position = False
    side = None
    entry_price = 0.0
    sl_price = 0.0
    tp_price = 0.0
    qty = 0.0
    entry_idx = -1
    pending_signal = None

    n = len(df)
    for i in range(n):
        # 1) Fill any pending signal at this bar's open
        if not in_position and pending_signal is not None:
            entry_open = float(o[i])
            if pending_signal == "long":
                fill = entry_open * (1.0 + slip)
                sl_price = fill * (1.0 - sl_pct)
                tp_price = fill * (1.0 + tp_pct)
            else:
                fill = entry_open * (1.0 - slip)
                sl_price = fill * (1.0 + sl_pct)
                tp_price = fill * (1.0 - tp_pct)
            notional = equity * pos_pct
            qty = notional / fill
            equity -= notional * fee  # entry fee only
            entry_price = fill
            side = pending_signal
            entry_idx = i
            in_position = True
            pending_signal = None

        # 2) Check SL/TP within this bar
        if in_position:
            hi = float(h[i])
            lo = float(l[i])
            if side == "long":
                hit_sl = lo <= sl_price
                hit_tp = hi >= tp_price
            else:
                hit_sl = hi >= sl_price
                hit_tp = lo <= tp_price

            exit_reason = None
            if hit_sl and hit_tp:
                exit_reason = "sl" if same_bar == "SL" else "tp"
            elif hit_sl:
                exit_reason = "sl"
            elif hit_tp:
                exit_reason = "tp"

            if exit_reason is not None:
                if exit_reason == "sl":
                    exit_price = sl_price * (1.0 - slip) if side == "long" else sl_price * (1.0 + slip)
                else:
                    exit_price = tp_price

                if side == "long":
                    gross_pnl = (exit_price - entry_price) * qty
                else:
                    gross_pnl = (entry_price - exit_price) * qty

                exit_fee = exit_price * qty * fee
                equity += gross_pnl - exit_fee
                pnl_net = gross_pnl - exit_fee - (entry_price * qty * fee)
                pnl_pct = pnl_net / (entry_price * qty)

                trades.append(Trade(
                    side=side,
                    entry_time=pd.Timestamp(ts[entry_idx]),
                    entry_price=entry_price,
                    exit_time=pd.Timestamp(ts[i]),
                    exit_price=exit_price,
                    exit_reason=exit_reason,
                    qty=qty,
                    pnl=pnl_net,
                    pnl_pct=pnl_pct,
                    bars_held=i - entry_idx,
                ))
                in_position = False
                side = None

        # 3) Latch signal for next bar's open (only when flat)
        if not in_position:
            s = sig[i]
            if s in ("long", "short"):
                pending_signal = s

        # 4) Mark-to-market equity for the curve
        if in_position:
            if side == "long":
                upnl = (float(c[i]) - entry_price) * qty
            else:
                upnl = (entry_price - float(c[i])) * qty
            mtm = equity + upnl
        else:
            mtm = equity
        equity_curve_ts.append(ts[i])
        equity_curve_eq.append(mtm)

    trades_df = pd.DataFrame([asdict(t) for t in trades])
    equity_df = pd.DataFrame({"timestamp": equity_curve_ts, "equity": equity_curve_eq})
    return trades_df, equity_df
