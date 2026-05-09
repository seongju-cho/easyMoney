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
    exit_reason: str   # 'tp', 'sl', 'opp'
    qty: float
    pnl: float
    pnl_pct: float
    bars_held: int
    stoch_k_signal: float
    stoch_d_signal: float
    atr_signal: float
    sl_distance: float
    tp_distance: float


def _stop_levels(side: str, fill: float, cfg: dict, atr_signal: float) -> tuple[float, float, float, float]:
    """Return (sl_price, tp_price, sl_distance_per_unit, tp_distance_per_unit)."""
    mode = str(cfg.get("stop_mode", "pct")).lower()
    if mode == "atr":
        sl_dist = float(cfg["atr_sl_mult"]) * float(atr_signal)
        tp_dist = float(cfg["atr_tp_mult"]) * float(atr_signal)
    else:  # pct
        sl_dist = fill * float(cfg["sl_pct"])
        tp_dist = fill * float(cfg["tp_pct"])
    if side == "long":
        return fill - sl_dist, fill + tp_dist, sl_dist, tp_dist
    else:
        return fill + sl_dist, fill - tp_dist, sl_dist, tp_dist


def _qty(equity: float, fill: float, sl_distance: float, cfg: dict) -> float:
    mode = str(cfg.get("sizing_mode", "notional_pct")).lower()
    if mode == "risk_pct":
        risk = float(cfg["risk_pct"]) * equity
        return risk / max(sl_distance, 1e-12)
    notional = equity * float(cfg.get("position_pct", 1.0))
    return notional / fill


def run_backtest(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Event-driven backtest. See README for rules."""
    equity = float(cfg["initial_capital"])
    fee = float(cfg["fee_pct"])
    slip = float(cfg["slippage_pct"])
    same_bar = str(cfg.get("same_bar_priority", "SL")).upper()
    exit_on_opp = bool(cfg.get("exit_on_opposite_signal", False))

    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    ts = df["timestamp"].to_numpy()
    sig = df["signal"].to_numpy()
    sk = df["stoch_k"].to_numpy() if "stoch_k" in df.columns else None
    sd = df["stoch_d"].to_numpy() if "stoch_d" in df.columns else None
    atr_arr = df["atr"].to_numpy() if "atr" in df.columns else None

    trades: list[Trade] = []
    eq_ts: list = []
    eq_val: list = []

    in_position = False
    side = None
    entry_price = 0.0
    sl_price = tp_price = 0.0
    sl_distance = tp_distance = 0.0
    qty = 0.0
    entry_idx = -1
    signal_idx = -1
    atr_signal = float("nan")

    pending_signal = None
    pending_signal_idx = -1
    pending_exit = False  # exit at next bar's open (opposite-signal exit)

    n = len(df)
    for i in range(n):
        # 1) Pending exit at this bar's open (opposite-signal exit fires before SL/TP check)
        if in_position and pending_exit:
            opn = float(o[i])
            exit_price = opn * (1.0 - slip) if side == "long" else opn * (1.0 + slip)
            gross_pnl = (exit_price - entry_price) * qty if side == "long" else (entry_price - exit_price) * qty
            exit_fee = exit_price * qty * fee
            equity += gross_pnl - exit_fee
            pnl_net = gross_pnl - exit_fee - (entry_price * qty * fee)
            pnl_pct = pnl_net / (entry_price * qty)
            trades.append(Trade(
                side=side, entry_time=pd.Timestamp(ts[entry_idx]), entry_price=entry_price,
                exit_time=pd.Timestamp(ts[i]), exit_price=exit_price, exit_reason="opp",
                qty=qty, pnl=pnl_net, pnl_pct=pnl_pct, bars_held=i - entry_idx,
                stoch_k_signal=float(sk[signal_idx]) if sk is not None else float("nan"),
                stoch_d_signal=float(sd[signal_idx]) if sd is not None else float("nan"),
                atr_signal=atr_signal,
                sl_distance=sl_distance, tp_distance=tp_distance,
            ))
            in_position = False
            side = None
            pending_exit = False

        # 2) Pending entry at this bar's open
        if not in_position and pending_signal is not None:
            entry_open = float(o[i])
            sig_idx = pending_signal_idx
            atr_at_sig = float(atr_arr[sig_idx]) if atr_arr is not None else float("nan")
            if pending_signal == "long":
                fill = entry_open * (1.0 + slip)
            else:
                fill = entry_open * (1.0 - slip)
            sl_price, tp_price, sl_distance, tp_distance = _stop_levels(pending_signal, fill, cfg, atr_at_sig)
            # Skip entries we cannot size (e.g., ATR not yet available)
            if not (sl_distance > 0):
                pending_signal = None
                pending_signal_idx = -1
            else:
                qty = _qty(equity, fill, sl_distance, cfg)
                # debit entry fee on notional
                equity -= fill * qty * fee
                entry_price = fill
                side = pending_signal
                entry_idx = i
                signal_idx = sig_idx
                atr_signal = atr_at_sig
                in_position = True
                pending_signal = None
                pending_signal_idx = -1

        # 3) SL/TP intrabar
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
                gross_pnl = (exit_price - entry_price) * qty if side == "long" else (entry_price - exit_price) * qty
                exit_fee = exit_price * qty * fee
                equity += gross_pnl - exit_fee
                pnl_net = gross_pnl - exit_fee - (entry_price * qty * fee)
                pnl_pct = pnl_net / (entry_price * qty)
                trades.append(Trade(
                    side=side, entry_time=pd.Timestamp(ts[entry_idx]), entry_price=entry_price,
                    exit_time=pd.Timestamp(ts[i]), exit_price=exit_price, exit_reason=exit_reason,
                    qty=qty, pnl=pnl_net, pnl_pct=pnl_pct, bars_held=i - entry_idx,
                    stoch_k_signal=float(sk[signal_idx]) if sk is not None else float("nan"),
                    stoch_d_signal=float(sd[signal_idx]) if sd is not None else float("nan"),
                    atr_signal=atr_signal,
                    sl_distance=sl_distance, tp_distance=tp_distance,
                ))
                in_position = False
                side = None
                pending_exit = False

        # 4) Latch signals at this bar's close
        s = sig[i]
        if not in_position:
            if s in ("long", "short"):
                pending_signal = s
                pending_signal_idx = i
        else:
            if exit_on_opp and s in ("long", "short") and s != side:
                pending_exit = True

        # 5) Mark-to-market for equity curve
        if in_position:
            upnl = (float(c[i]) - entry_price) * qty if side == "long" else (entry_price - float(c[i])) * qty
            mtm = equity + upnl
        else:
            mtm = equity
        eq_ts.append(ts[i])
        eq_val.append(mtm)

    trades_df = pd.DataFrame([asdict(t) for t in trades])
    equity_df = pd.DataFrame({"timestamp": eq_ts, "equity": eq_val})
    return trades_df, equity_df
