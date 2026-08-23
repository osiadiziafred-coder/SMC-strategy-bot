from __future__ import annotations

import os

import pandas as pd

from smc_robot.broker.base import Broker
from smc_robot.config import Position, Side


class Mt5Broker(Broker):
    """MetaTrader 5 adapter for live XAUUSDm trading (Windows terminal)."""

    def __init__(
        self,
        login: int | None = None,
        password: str | None = None,
        server: str | None = None,
        path: str | None = None,
    ) -> None:
        try:
            import MetaTrader5 as mt5  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "MetaTrader5 is not installed. Live mode requires a Windows MT5 terminal "
                "and: pip install 'fredfx-v1-smc[mt5]'"
            ) from exc
        self._mt5 = mt5
        self.login = int(login or os.getenv("MT5_LOGIN", "0"))
        self.password = password or os.getenv("MT5_PASSWORD", "")
        self.server = server or os.getenv("MT5_SERVER", "")
        self.path = path or os.getenv("MT5_PATH") or None

    def connect(self) -> None:
        kwargs = {}
        if self.path:
            kwargs["path"] = self.path
        if not self._mt5.initialize(**kwargs):
            raise RuntimeError(f"MT5 initialize failed: {self._mt5.last_error()}")
        if self.login and self.password and self.server:
            if not self._mt5.login(self.login, password=self.password, server=self.server):
                raise RuntimeError(f"MT5 login failed: {self._mt5.last_error()}")

    def shutdown(self) -> None:
        self._mt5.shutdown()

    def balance(self) -> float:
        info = self._mt5.account_info()
        if info is None:
            raise RuntimeError("MT5 account_info failed")
        return float(info.balance)

    def candles(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        tf = getattr(self._mt5, f"TIMEFRAME_{timeframe}")
        rates = self._mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None:
            raise RuntimeError(f"No candles for {symbol} {timeframe}: {self._mt5.last_error()}")
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        return df[["time", "open", "high", "low", "close", "tick_volume"]].rename(
            columns={"tick_volume": "volume"}
        )

    def open_positions(self, magic: int | None = None) -> list[Position]:
        positions = self._mt5.positions_get() or []
        out: list[Position] = []
        for pos in positions:
            if magic is not None and int(pos.magic) != magic:
                continue
            side: Side = "buy" if pos.type == self._mt5.ORDER_TYPE_BUY else "sell"
            out.append(
                Position(
                    ticket=int(pos.ticket),
                    side=side,
                    volume=float(pos.volume),
                    entry=float(pos.price_open),
                    sl=float(pos.sl),
                    tp=float(pos.tp),
                    initial_sl=float(pos.sl),
                    opened_at=pos.time,
                    comment=str(pos.comment),
                    magic=int(pos.magic),
                )
            )
        return out

    def open_trade(
        self,
        symbol: str,
        side: Side,
        volume: float,
        sl: float,
        tp: float,
        comment: str,
        magic: int,
    ) -> Position:
        if self.open_positions(magic):
            raise RuntimeError("Robot already has an open position")
        info = self._mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"Unknown symbol {symbol}")
        if not info.visible:
            self._mt5.symbol_select(symbol, True)
        tick = self._mt5.symbol_info_tick(symbol)
        price = float(tick.ask if side == "buy" else tick.bid)
        order_type = self._mt5.ORDER_TYPE_BUY if side == "buy" else self._mt5.ORDER_TYPE_SELL
        request = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": price,
            "sl": float(sl),
            "tp": float(tp),
            "deviation": 30,
            "magic": magic,
            "comment": comment,
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._mt5.ORDER_FILLING_IOC,
        }
        result = self._mt5.order_send(request)
        if result is None or result.retcode != self._mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"order_send failed: {result}")
        return Position(
            ticket=int(result.order),
            side=side,
            volume=volume,
            entry=float(result.price),
            sl=sl,
            tp=tp,
            initial_sl=sl,
            opened_at=result.time if hasattr(result, "time") else None,
            comment=comment,
            magic=magic,
        )

    def modify_sl(self, ticket: int, sl: float) -> None:
        positions = self._mt5.positions_get(ticket=ticket)
        if not positions:
            raise RuntimeError(f"Position {ticket} not found")
        pos = positions[0]
        request = {
            "action": self._mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": pos.symbol,
            "sl": float(sl),
            "tp": float(pos.tp),
        }
        result = self._mt5.order_send(request)
        if result is None or result.retcode != self._mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"modify SL failed: {result}")

    def bid_ask(self, symbol: str) -> tuple[float, float]:
        tick = self._mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"No tick for {symbol}")
        return float(tick.bid), float(tick.ask)
