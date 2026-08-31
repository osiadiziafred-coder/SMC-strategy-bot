from __future__ import annotations

from datetime import datetime, timezone

from smc_robot.broker.base import Broker
from smc_robot.models import Candle, Direction, Position
from smc_robot.risk.protection import Quote
from smc_robot.risk.sizing import SymbolSpec

TF_MAP = {
    "M15": 15,
    "M30": 30,
    "H1": 16385,
}


class MT5Broker(Broker):
    """Live MetaTrader 5 execution adapter. Requires the MetaTrader5 package (Windows)."""

    def __init__(
        self,
        login: int | None = None,
        password: str | None = None,
        server: str | None = None,
        path: str | None = None,
    ):
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self._mt5 = None

    def connect(self) -> None:
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise RuntimeError(
                "MetaTrader5 is not installed. Install it on Windows with "
                "`pip install MetaTrader5`, or run with --mode paper/dry."
            ) from exc
        self._mt5 = mt5
        initialized = mt5.initialize(self.path) if self.path else mt5.initialize()
        if not initialized:
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
        if self.login:
            if not mt5.login(self.login, password=self.password or "", server=self.server or ""):
                raise RuntimeError(f"MT5 login failed: {mt5.last_error()}")

    def shutdown(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()

    def _require(self):
        if self._mt5 is None:
            raise RuntimeError("MT5 is not connected")
        return self._mt5

    def symbol_spec(self, symbol: str) -> SymbolSpec:
        mt5 = self._require()
        info = mt5.symbol_info(symbol)
        if info is None:
            if not mt5.symbol_select(symbol, True):
                raise RuntimeError(f"Unknown symbol {symbol}")
            info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"Cannot load symbol {symbol}")
        if str(info.name) != symbol:
            raise RuntimeError(f"Exact symbol {symbol} not found (broker returned {info.name})")
        tick = mt5.symbol_info_tick(symbol)
        bid = float(getattr(tick, "bid", 0) or getattr(info, "bid", 0) or 0.0) if tick is not None else float(getattr(info, "bid", 0) or 0.0)
        ask = float(getattr(tick, "ask", 0) or getattr(info, "ask", 0) or 0.0) if tick is not None else float(getattr(info, "ask", 0) or 0.0)
        point = float(info.point)
        spread_pts = float(getattr(info, "spread", 0) or 0.0)
        if spread_pts <= 0 and point > 0 and bid > 0 and ask >= bid:
            spread_pts = (ask - bid) / point
        return SymbolSpec(
            name=str(info.name),
            point=point,
            digits=int(info.digits),
            volume_min=float(info.volume_min),
            volume_max=float(info.volume_max),
            volume_step=float(info.volume_step),
            trade_stops_level=int(info.trade_stops_level),
            filling_mode=int(info.filling_mode),
            tick_size=float(getattr(info, "trade_tick_size", 0) or info.point),
            tick_value=float(getattr(info, "trade_tick_value", 0) or 1.0),
            margin_initial=float(getattr(info, "margin_initial", 0) or 0.0),
            trade_mode=_trade_mode_name(mt5, getattr(info, "trade_mode", 4)),
            spread=spread_pts,
            bid=bid,
            ask=ask,
        )

    def account_balance(self) -> float:
        mt5 = self._require()
        info = mt5.account_info()
        if info is None:
            raise RuntimeError(f"account_info failed: {mt5.last_error()}")
        return float(info.balance)

    def candles(self, symbol: str, timeframe: str, count: int) -> list[Candle]:
        mt5 = self._require()
        tf = TF_MAP[timeframe]
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None:
            raise RuntimeError(f"copy_rates failed: {mt5.last_error()}")
        candles: list[Candle] = []
        for row in rates:
            candles.append(
                Candle(
                    time=datetime.fromtimestamp(int(row["time"]), tz=timezone.utc),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["tick_volume"]),
                    spread=float(row["spread"]) if "spread" in row.dtype.names else 0.0,
                )
            )
        return candles

    def quote(self, symbol: str) -> Quote:
        mt5 = self._require()
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick is None or info is None:
            raise RuntimeError(f"quote failed: {mt5.last_error()}")
        point = float(info.point) or 0.01
        spread = (float(tick.ask) - float(tick.bid)) / point
        ts = datetime.fromtimestamp(int(tick.time), tz=timezone.utc)
        return Quote(bid=float(tick.bid), ask=float(tick.ask), time=ts, spread_points=spread)

    def open_positions(self, symbol: str, magic: int) -> list[Position]:
        mt5 = self._require()
        positions = mt5.positions_get(symbol=symbol)
        if positions is None:
            return []
        out: list[Position] = []
        for pos in positions:
            if int(pos.magic) != magic:
                continue
            direction = Direction.BUY if pos.type == 0 else Direction.SELL
            entry = float(pos.price_open)
            sl = float(pos.sl)
            out.append(
                Position(
                    ticket=int(pos.ticket),
                    symbol=pos.symbol,
                    direction=direction,
                    volume=float(pos.volume),
                    entry=entry,
                    sl=sl,
                    tp=float(pos.tp),
                    initial_sl=sl,
                    initial_risk=abs(entry - sl),
                    magic=int(pos.magic),
                    comment=str(pos.comment),
                )
            )
        return out

    def market_order(
        self,
        symbol: str,
        direction: Direction,
        lots: float,
        sl: float,
        tp: float,
        deviation_points: int,
        magic: int,
        comment: str,
    ) -> Position:
        mt5 = self._require()
        spec = self.symbol_spec(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError("No tick for order")
        order_type = mt5.ORDER_TYPE_BUY if direction == Direction.BUY else mt5.ORDER_TYPE_SELL
        price = float(tick.ask) if direction == Direction.BUY else float(tick.bid)
        filling = _filling_mode(mt5, spec.filling_mode)
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lots,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": deviation_points,
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            code = getattr(result, "retcode", None)
            raise RuntimeError(f"order_send failed: {code} {mt5.last_error()}")
        fill = float(result.price) if result.price else price
        ticket = int(result.order)
        return Position(
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            volume=lots,
            entry=fill,
            sl=sl,
            tp=tp,
            initial_sl=sl,
            initial_risk=abs(fill - sl),
            magic=magic,
            comment=comment,
        )

    def modify_sl(self, position: Position, sl: float) -> Position:
        mt5 = self._require()
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": position.ticket,
            "sl": sl,
            "tp": position.tp,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"modify SL failed: {mt5.last_error()}")
        return position.model_copy(update={"sl": sl, "breakeven_applied": True})


def _trade_mode_name(mt5, raw) -> str:
    mapping = {
        int(getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", 0)): "disabled",
        int(getattr(mt5, "SYMBOL_TRADE_MODE_LONGONLY", 1)): "longonly",
        int(getattr(mt5, "SYMBOL_TRADE_MODE_SHORTONLY", 2)): "shortonly",
        int(getattr(mt5, "SYMBOL_TRADE_MODE_CLOSEONLY", 3)): "closeonly",
        int(getattr(mt5, "SYMBOL_TRADE_MODE_FULL", 4)): "full",
    }
    if isinstance(raw, str) and not raw.isdigit():
        return raw
    try:
        return mapping.get(int(raw), str(raw))
    except (TypeError, ValueError):
        return str(raw)


def _filling_mode(mt5, filling_mode: int) -> int:
    ioc = getattr(mt5, "SYMBOL_FILLING_IOC", 1)
    fok = getattr(mt5, "SYMBOL_FILLING_FOK", 2)
    ret = getattr(mt5, "SYMBOL_FILLING_RETURN", 4)
    if filling_mode & ioc:
        return mt5.ORDER_FILLING_IOC
    if filling_mode & fok:
        return mt5.ORDER_FILLING_FOK
    if filling_mode & ret:
        return mt5.ORDER_FILLING_RETURN
    return mt5.ORDER_FILLING_IOC
