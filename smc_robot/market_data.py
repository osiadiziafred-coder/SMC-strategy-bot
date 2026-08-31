"""Collect H1 / M30 / M15 and verify the exact MT5 symbol exists."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from smc_robot.broker.base import Broker
from smc_robot.config import Settings
from smc_robot.models import Candle
from smc_robot.risk.protection import Quote
from smc_robot.risk.sizing import SymbolSpec

REQUIRED_SYMBOL = "XAUUSDm"


def symbol_snapshot(spec: SymbolSpec, quote: Quote | None = None) -> dict[str, Any]:
    """Broker fields Python must read before any trade."""
    bid = quote.bid if quote is not None else spec.bid
    ask = quote.ask if quote is not None else spec.ask
    spread = quote.spread_points if quote is not None else spec.spread
    return {
        "symbol": spec.name,
        "bid": bid,
        "ask": ask,
        "point": spec.point,
        "digits": spec.digits,
        "volume_min": spec.volume_min,
        "volume_max": spec.volume_max,
        "volume_step": spec.volume_step,
        "spread": spread,
        "trade_mode": spec.trade_mode,
        "trade_stops_level": spec.trade_stops_level,
        "tick_size": spec.tick_size,
        "tick_value": spec.tick_value,
    }


def verify_symbol(broker: Broker, symbol: str = REQUIRED_SYMBOL) -> SymbolSpec:
    """Fail closed unless the exact symbol exists and has usable lot/price specs."""
    try:
        spec = broker.symbol_spec(symbol)
    except Exception as exc:
        raise RuntimeError(f"symbol_unavailable:{symbol}:{exc}") from exc
    if spec.name != symbol:
        raise RuntimeError(f"symbol_unavailable: requested {symbol}, broker returned {spec.name}")
    if spec.point <= 0 or spec.digits < 0:
        raise RuntimeError(f"invalid_price: bad point/digits for {symbol}")
    if spec.volume_min <= 0 or spec.volume_step <= 0 or spec.volume_max < spec.volume_min:
        raise RuntimeError(f"invalid_lot: broker volume limits for {symbol}")
    if spec.trade_mode.lower() in {"disabled", "0"}:
        raise RuntimeError(f"symbol_unavailable: trade_mode={spec.trade_mode}")
    return spec


def verify_quote(quote: Quote) -> None:
    if quote.bid <= 0 or quote.ask <= 0 or quote.ask < quote.bid:
        raise RuntimeError("invalid_price")


def load_mtf(
    broker: Broker,
    settings: Settings,
    symbol: str | None = None,
) -> tuple[list[Candle], list[Candle], list[Candle]]:
    """H1 bias → M30 confirmation → M15 entry. All three required."""
    name = symbol or settings.symbol
    h1 = broker.candles(name, settings.timeframes.bias, settings.bars.h1)
    m30 = broker.candles(name, settings.timeframes.confirm, settings.bars.m30)
    m15 = broker.candles(name, settings.timeframes.entry, settings.bars.m15)
    if not h1 or not m30 or not m15:
        raise RuntimeError("incomplete_market_data")
    return h1, m30, m15


def inspect_market(
    broker: Broker,
    settings: Settings,
) -> tuple[SymbolSpec, Quote, dict[str, Any]]:
    spec = verify_symbol(broker, settings.symbol)
    quote = broker.quote(settings.symbol)
    verify_quote(quote)
    snap = symbol_snapshot(spec, quote)
    snap["asdict"] = asdict(spec)
    return spec, quote, snap
