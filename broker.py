"""MetaTrader 5 broker interface."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from config import Config, Timeframe

logger = logging.getLogger(__name__)

try:
  import MetaTrader5 as mt5

  MT5_AVAILABLE = True
except ImportError:
  mt5 = None  # type: ignore
  MT5_AVAILABLE = False


MT5_TF_MAP: dict[Timeframe, Any] = {}


def _init_mt5_tf_map() -> None:
  if not MT5_AVAILABLE:
    return
  MT5_TF_MAP[Timeframe.M5] = mt5.TIMEFRAME_M5
  MT5_TF_MAP[Timeframe.M15] = mt5.TIMEFRAME_M15
  MT5_TF_MAP[Timeframe.H1] = mt5.TIMEFRAME_H1


@dataclass
class Position:
  ticket: int
  symbol: str
  direction: str  # "buy" or "sell"
  volume: float
  entry_price: float
  sl: float
  tp: float
  profit: float


@dataclass
class OrderResult:
  success: bool
  ticket: int = 0
  message: str = ""


class Broker:
  """Wraps MetaTrader 5 order and data operations."""

  def __init__(self, config: Config) -> None:
    self.config = config
    self._connected = False
    _init_mt5_tf_map()

  def connect(self) -> bool:
    if not MT5_AVAILABLE:
      logger.error("MetaTrader5 package not installed. Run: pip install MetaTrader5")
      return False

    kwargs: dict[str, Any] = {}
    if self.config.mt5_path:
      kwargs["path"] = self.config.mt5_path

    if not mt5.initialize(**kwargs):
      logger.error("MT5 initialize failed: %s", mt5.last_error())
      return False

    if self.config.mt5_login:
      if not mt5.login(
        self.config.mt5_login,
        password=self.config.mt5_password,
        server=self.config.mt5_server,
      ):
        logger.error("MT5 login failed: %s", mt5.last_error())
        mt5.shutdown()
        return False

    info = mt5.account_info()
    if info is None:
      logger.error("Could not retrieve account info")
      return False

    self._connected = True
    logger.info(
      "Connected to MT5 — account %s, balance %.2f %s",
      info.login,
      info.balance,
      info.currency,
    )
    return True

  def disconnect(self) -> None:
    if MT5_AVAILABLE and self._connected:
      mt5.shutdown()
      self._connected = False

  @property
  def is_connected(self) -> bool:
    return self._connected

  def get_balance(self) -> float:
    if not MT5_AVAILABLE or not self._connected:
      return 0.0
    info = mt5.account_info()
    return info.balance if info else 0.0

  def get_candles(self, timeframe: Timeframe, count: int) -> pd.DataFrame:
    """Fetch OHLCV candles as a DataFrame indexed by time."""
    if not MT5_AVAILABLE or not self._connected:
      return pd.DataFrame()

    tf = MT5_TF_MAP.get(timeframe)
    rates = mt5.copy_rates_from_pos(self.config.symbol, tf, 0, count)
    if rates is None or len(rates) == 0:
      logger.warning("No candle data for %s %s", self.config.symbol, timeframe.value)
      return pd.DataFrame()

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    df.rename(
      columns={
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "tick_volume": "volume",
      },
      inplace=True,
    )
    return df[["open", "high", "low", "close", "volume"]]

  def get_open_positions(self, symbol: str | None = None) -> list[Position]:
    if not MT5_AVAILABLE or not self._connected:
      return []

    sym = symbol or self.config.symbol
    positions = mt5.positions_get(symbol=sym)
    if positions is None:
      return []

    result: list[Position] = []
    for p in positions:
      direction = "buy" if p.type == mt5.ORDER_TYPE_BUY else "sell"
      result.append(
        Position(
          ticket=p.ticket,
          symbol=p.symbol,
          direction=direction,
          volume=p.volume,
          entry_price=p.price_open,
          sl=p.sl,
          tp=p.tp,
          profit=p.profit,
        )
      )
    return result

  def _symbol_info(self) -> Any:
    return mt5.symbol_info(self.config.symbol)

  def _normalize_price(self, price: float) -> float:
    info = self._symbol_info()
    if info is None:
      return round(price, 2)
    return round(price, info.digits)

  def _normalize_volume(self, volume: float) -> float:
    info = self._symbol_info()
    if info is None:
      return volume
    step = info.volume_step
    return round(max(info.volume_min, min(volume, info.volume_max)) / step) * step

  def place_order(
    self,
    direction: str,
    volume: float,
    sl: float,
    tp: float,
    comment: str = "SMC_Robot",
  ) -> OrderResult:
    if not MT5_AVAILABLE or not self._connected:
      return OrderResult(success=False, message="Not connected to MT5")

    sym = self.config.symbol
    if not mt5.symbol_select(sym, True):
      return OrderResult(success=False, message=f"Symbol {sym} not available")

    tick = mt5.symbol_info_tick(sym)
    if tick is None:
      return OrderResult(success=False, message="No tick data")

    order_type = mt5.ORDER_TYPE_BUY if direction == "buy" else mt5.ORDER_TYPE_SELL
    price = tick.ask if direction == "buy" else tick.bid

    request = {
      "action": mt5.TRADE_ACTION_DEAL,
      "symbol": sym,
      "volume": self._normalize_volume(volume),
      "type": order_type,
      "price": price,
      "sl": self._normalize_price(sl),
      "tp": self._normalize_price(tp),
      "deviation": 20,
      "magic": 20260820,
      "comment": comment,
      "type_time": mt5.ORDER_TIME_GTC,
      "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
      return OrderResult(success=False, message=str(mt5.last_error()))

    if result.retcode != mt5.TRADE_RETCODE_DONE:
      return OrderResult(success=False, message=f"Order failed: {result.retcode} — {result.comment}")

    logger.info(
      "Order placed: %s %.2f lots @ %.2f | SL %.2f | TP %.2f | ticket %d",
      direction.upper(),
      volume,
      price,
      sl,
      tp,
      result.order,
    )
    return OrderResult(success=True, ticket=result.order, message="OK")

  def modify_sl(self, ticket: int, new_sl: float) -> OrderResult:
    if not MT5_AVAILABLE or not self._connected:
      return OrderResult(success=False, message="Not connected")

    positions = mt5.positions_get(ticket=ticket)
    if not positions:
      return OrderResult(success=False, message=f"Position {ticket} not found")

    pos = positions[0]
    request = {
      "action": mt5.TRADE_ACTION_SLTP,
      "symbol": pos.symbol,
      "position": ticket,
      "sl": self._normalize_price(new_sl),
      "tp": pos.tp,
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
      msg = str(mt5.last_error()) if result is None else result.comment
      return OrderResult(success=False, message=msg)

    logger.info("SL modified for ticket %d → %.2f", ticket, new_sl)
    return OrderResult(success=True, ticket=ticket, message="SL updated")

  def current_price(self) -> tuple[float, float]:
    """Return (bid, ask)."""
    if not MT5_AVAILABLE or not self._connected:
      return 0.0, 0.0
    tick = mt5.symbol_info_tick(self.config.symbol)
    if tick is None:
      return 0.0, 0.0
    return tick.bid, tick.ask
