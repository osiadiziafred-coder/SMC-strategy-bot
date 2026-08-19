"""Optional MetaTrader 5 live adapter. Requires Windows + MetaTrader5 terminal."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import pandas as pd

from smc_robot.broker.base import AccountState, Broker, Position
from smc_robot.config import RobotConfig

Side = Literal["buy", "sell"]

TF_MINUTES = {"M5": 5, "M15": 15, "H1": 60}


class MT5Broker(Broker):
    def __init__(self, config: RobotConfig | None = None) -> None:
        try:
            import MetaTrader5 as mt5  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "MetaTrader5 is not installed. Live mode needs the official "
                "MetaTrader5 Python package on a Windows machine with MT5 running."
            ) from exc
        self._mt5 = mt5
        self.config = config or RobotConfig()
        self.symbol = self.config.symbol
        if not mt5.initialize():
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
        if not mt5.symbol_select(self.symbol, True):
            raise RuntimeError(f"symbol {self.symbol} not found in Market Watch")

    def account(self) -> AccountState:
        info = self._mt5.account_info()
        if info is None:
            raise RuntimeError(f"account_info failed: {self._mt5.last_error()}")
        positions = [self._from_mt5(p) for p in self._mt5.positions_get(symbol=self.symbol) or []]
        return AccountState(balance=float(info.balance), equity=float(info.equity), positions=positions)

    def candles(self, timeframe: str, count: int = 300) -> pd.DataFrame:
        tf_map = {
            "M5": self._mt5.TIMEFRAME_M5,
            "M15": self._mt5.TIMEFRAME_M15,
            "H1": self._mt5.TIMEFRAME_H1,
        }
        if timeframe not in tf_map:
            raise ValueError(f"unsupported timeframe {timeframe}")
        rates = self._mt5.copy_rates_from_pos(self.symbol, tf_map[timeframe], 0, count)
        if rates is None:
            raise RuntimeError(f"copy_rates failed: {self._mt5.last_error()}")
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        return df[["time", "open", "high", "low", "close", "tick_volume"]].rename(
            columns={"tick_volume": "volume"}
        )

    def bid_ask(self) -> tuple[float, float]:
        tick = self._mt5.symbol_info_tick(self.symbol)
        if tick is None:
            raise RuntimeError(f"no tick for {self.symbol}")
        return float(tick.bid), float(tick.ask)

    def open_trade(
        self,
        side: Side,
        volume: float,
        sl: float,
        tp: float,
        timeframe: str,
        comment: str = "",
    ) -> Position:
        bid, ask = self.bid_ask()
        order_type = self._mt5.ORDER_TYPE_BUY if side == "buy" else self._mt5.ORDER_TYPE_SELL
        price = ask if side == "buy" else bid
        request = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": self.config.deviation_points,
            "magic": self.config.magic,
            "comment": comment or f"SMC {timeframe}",
            "type_filling": self._mt5.ORDER_FILLING_IOC,
        }
        result = self._mt5.order_send(request)
        if result is None or result.retcode != self._mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"order_send failed: {result}")
        return Position(
            ticket=int(result.order),
            symbol=self.symbol,
            side=side,
            volume=volume,
            entry=float(result.price),
            sl=sl,
            tp=tp,
            timeframe=timeframe,
            opened_at=datetime.now(timezone.utc),
            original_sl=sl,
            original_risk=abs(float(result.price) - sl),
            comment=comment,
        )

    def modify_sl(self, ticket: int, sl: float) -> None:
        positions = self._mt5.positions_get(ticket=ticket)
        if not positions:
            raise KeyError(f"ticket {ticket} not found")
        pos = positions[0]
        request = {
            "action": self._mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": self.symbol,
            "sl": sl,
            "tp": float(pos.tp),
            "magic": self.config.magic,
        }
        result = self._mt5.order_send(request)
        if result is None or result.retcode != self._mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"modify SL failed: {result}")

    def close_trade(self, ticket: int, reason: str = "manual") -> Position:
        positions = self._mt5.positions_get(ticket=ticket)
        if not positions:
            raise KeyError(f"ticket {ticket} not found")
        pos = positions[0]
        side: Side = "buy" if pos.type == self._mt5.POSITION_TYPE_BUY else "sell"
        close_type = self._mt5.ORDER_TYPE_SELL if side == "buy" else self._mt5.ORDER_TYPE_BUY
        bid, ask = self.bid_ask()
        price = bid if side == "buy" else ask
        request = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": float(pos.volume),
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": self.config.deviation_points,
            "magic": self.config.magic,
            "comment": reason,
        }
        result = self._mt5.order_send(request)
        if result is None or result.retcode != self._mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"close failed: {result}")
        mapped = self._from_mt5(pos)
        mapped.closed = True
        mapped.exit_price = float(result.price)
        mapped.exit_reason = reason
        return mapped

    def _from_mt5(self, pos: object) -> Position:
        side: Side = "buy" if pos.type == self._mt5.POSITION_TYPE_BUY else "sell"  # type: ignore[attr-defined]
        entry = float(pos.price_open)  # type: ignore[attr-defined]
        sl = float(pos.sl)  # type: ignore[attr-defined]
        return Position(
            ticket=int(pos.ticket),  # type: ignore[attr-defined]
            symbol=str(pos.symbol),  # type: ignore[attr-defined]
            side=side,
            volume=float(pos.volume),  # type: ignore[attr-defined]
            entry=entry,
            sl=sl,
            tp=float(pos.tp),  # type: ignore[attr-defined]
            timeframe=_tf_from_comment(str(getattr(pos, "comment", ""))),
            opened_at=datetime.fromtimestamp(int(pos.time), tz=timezone.utc),  # type: ignore[attr-defined]
            original_sl=sl,
            original_risk=abs(entry - sl) or 0.01,
            comment=str(getattr(pos, "comment", "")),
        )


def _tf_from_comment(comment: str) -> str:
    for tf in ("M5", "M15", "H1"):
        if tf in comment:
            return tf
    return "M5"
