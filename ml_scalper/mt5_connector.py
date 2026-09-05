"""Market-data connectors: live MT5, offline synthetic, CSV.

The synthetic feed is generated at M1 and resampled to M5/M15 so multi-timeframe
relationships are internally consistent. Replay mode exposes a cutoff timestamp
so the live brain can be stepped bar-by-bar without a terminal.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config

_TF_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
OHLCV_COLUMNS = ["open", "high", "low", "close", "tick_volume", "spread"]


class BaseConnector:
    def connect(self) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def shutdown(self) -> None:
        pass

    def get_rates(self, timeframe: str, count: int) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError

    def get_tick(self, symbol: str) -> dict:  # pragma: no cover
        raise NotImplementedError

    def symbol_info(self, symbol: str) -> dict:  # pragma: no cover
        raise NotImplementedError

    def account_info(self) -> dict:  # pragma: no cover
        raise NotImplementedError

    def common_files_path(self) -> Path | None:
        return None


class MT5Connector(BaseConnector):
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._mt5 = None

    def _lib(self):
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5  # type: ignore
            except Exception as exc:  # pragma: no cover
                raise RuntimeError(
                    "MetaTrader5 package is unavailable (Windows-only). Use "
                    "data_source='synthetic' or 'csv' for offline training/testing."
                ) from exc
            self._mt5 = mt5
        return self._mt5

    def _tf_const(self, timeframe: str):
        mt5 = self._lib()
        return getattr(mt5, f"TIMEFRAME_{timeframe}")

    def connect(self) -> bool:  # pragma: no cover
        mt5 = self._lib()
        if not mt5.initialize():
            raise RuntimeError(f"MT5 initialize() failed: {mt5.last_error()}")
        if not mt5.symbol_select(self.cfg.symbol, True):
            raise RuntimeError(f"Could not select symbol {self.cfg.symbol}")
        return True

    def shutdown(self) -> None:  # pragma: no cover
        if self._mt5 is not None:
            self._mt5.shutdown()

    def get_rates(self, timeframe: str, count: int) -> pd.DataFrame:  # pragma: no cover
        mt5 = self._lib()
        rates = mt5.copy_rates_from_pos(self.cfg.symbol, self._tf_const(timeframe), 0, count)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"No rates returned for {self.cfg.symbol} {timeframe}")
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.set_index("time")
        if "spread" not in df.columns:
            df["spread"] = 0.0
        cols = [c for c in OHLCV_COLUMNS if c in df.columns]
        return df[cols].astype(float)

    def get_tick(self, symbol: str) -> dict:  # pragma: no cover
        mt5 = self._lib()
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        point = info.point if info else self.cfg.point
        spread_points = (tick.ask - tick.bid) / point if point else 0.0
        return {"bid": tick.bid, "ask": tick.ask, "spread_points": spread_points, "time": tick.time}

    def symbol_info(self, symbol: str) -> dict:  # pragma: no cover
        mt5 = self._lib()
        info = mt5.symbol_info(symbol)
        return {
            "point": info.point,
            "digits": info.digits,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "trade_contract_size": info.trade_contract_size,
            "trade_mode": int(info.trade_mode),
        }

    def account_info(self) -> dict:  # pragma: no cover
        mt5 = self._lib()
        acc = mt5.account_info()
        return {
            "balance": acc.balance,
            "equity": acc.equity,
            "margin_free": acc.margin_free,
            "margin_level": acc.margin_level,
            "currency": acc.currency,
            "trade_allowed": bool(acc.trade_allowed),
        }

    def common_files_path(self) -> Path | None:  # pragma: no cover
        mt5 = self._lib()
        info = mt5.terminal_info()
        if info and getattr(info, "commondata_path", None):
            return Path(info.commondata_path) / "Files" / "ml_scalper_bridge"
        return None


class SyntheticConnector(BaseConnector):
    def __init__(self, cfg: Config, n_m1: int | None = None, seed: int = 7, balance: float = 1000.0):
        self.cfg = cfg
        self.seed = seed
        self._balance = balance
        needed_m5 = max(cfg.train_bars, cfg.live_bars) + 400
        self.n_m1 = int(n_m1 or max(needed_m5 * 5 + 2000, 20_000))
        self._cache: dict[str, pd.DataFrame] = {}
        self._cutoff_time = None

    def connect(self) -> bool:
        self._build()
        return True

    def timeline(self) -> pd.DatetimeIndex:
        self._build()
        return self._cache["M5"].index

    def set_cutoff_time(self, ts) -> None:
        self._cutoff_time = ts

    def _build(self) -> None:
        if self._cache:
            return
        rng = np.random.default_rng(self.seed)
        n = self.n_m1
        preset = self.cfg.symbol_preset()
        start_price = preset["start_price"]
        vol = preset["vol"]
        spread_lo, spread_hi = preset["spread_range"]
        drift_scale = vol / 0.0011
        phase = np.linspace(0.0, 80.0 * np.pi, n)
        drift = (0.00055 * np.sin(phase) + 0.00018 * np.sin(phase * 0.25)) * drift_scale
        shocks = rng.normal(0.0, vol, n)
        phi = 0.34
        kappa = 2.8e-4
        log_start = np.log(start_price)
        logp = np.empty(n)
        logp[0] = log_start
        lr_prev = drift[0] + shocks[0]
        for t in range(1, n):
            pull = -kappa * (logp[t - 1] - log_start)
            lr = phi * lr_prev + drift[t] + pull + shocks[t]
            logp[t] = logp[t - 1] + lr
            lr_prev = lr
        close = np.exp(logp)
        open_ = np.empty(n)
        open_[0] = start_price
        open_[1:] = close[:-1]
        body_hi = np.maximum(open_, close)
        body_lo = np.minimum(open_, close)
        up_wick = np.abs(rng.normal(0.0, vol * 0.65, n)) * close
        dn_wick = np.abs(rng.normal(0.0, vol * 0.65, n)) * close
        high = body_hi + up_wick
        low = body_lo - dn_wick
        tick_volume = rng.integers(40, 400, n).astype(float)
        spread = np.round(rng.uniform(spread_lo, spread_hi, n))
        index = pd.date_range("2023-01-01", periods=n, freq="1min", name="time")
        m1 = pd.DataFrame(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "tick_volume": tick_volume,
                "spread": spread,
            },
            index=index,
        ).round(5)
        self._cache["M1"] = m1
        self._cache["M5"] = self._resample(m1, "5min")
        self._cache["M15"] = self._resample(m1, "15min")

    @staticmethod
    def _resample(m1: pd.DataFrame, rule: str) -> pd.DataFrame:
        agg = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "tick_volume": "sum",
            "spread": "mean",
        }
        return m1.resample(rule, label="right", closed="right").agg(agg).dropna().round(5)

    def get_rates(self, timeframe: str, count: int) -> pd.DataFrame:
        self._build()
        if timeframe not in self._cache:
            raise ValueError(f"Unsupported timeframe {timeframe}")
        df = self._cache[timeframe]
        if self._cutoff_time is not None:
            df = df[df.index <= self._cutoff_time]
        return df.iloc[-count:].copy()

    def get_tick(self, symbol: str) -> dict:
        self._build()
        last = self.get_rates("M1" if "M1" in self._cache else "M5", 1).iloc[-1]
        point = self.cfg.point
        spread_points = float(last["spread"])
        bid = float(last["close"])
        ask = bid + spread_points * point
        return {"bid": bid, "ask": ask, "spread_points": spread_points, "time": None}

    def symbol_info(self, symbol: str) -> dict:
        preset = self.cfg.symbol_preset()
        return {
            "point": self.cfg.point,
            "digits": self.cfg.digits,
            "volume_min": self.cfg.min_lot,
            "volume_max": self.cfg.max_lot,
            "volume_step": self.cfg.lot_step,
            "trade_contract_size": preset.get("contract_size", 1.0),
            "trade_mode": 4,
        }

    def account_info(self) -> dict:
        return {
            "balance": self._balance,
            "equity": self._balance,
            "margin_free": self._balance,
            "margin_level": 0.0,
            "currency": "USD",
            "trade_allowed": True,
        }


class CSVConnector(BaseConnector):
    def __init__(self, cfg: Config, balance: float = 1000.0):
        self.cfg = cfg
        self._balance = balance

    def connect(self) -> bool:
        return True

    def get_rates(self, timeframe: str, count: int) -> pd.DataFrame:
        path = Path(self.cfg.csv_dir) / f"{self.cfg.symbol}_{timeframe}.csv"
        if not path.exists():
            # also try the instrument slug
            from .config import instrument_slug

            alt = Path(self.cfg.csv_dir) / f"{instrument_slug(self.cfg.symbol)}_{timeframe}.csv"
            path = alt if alt.exists() else path
        if not path.exists():
            raise FileNotFoundError(f"CSV not found: {path}")
        df = pd.read_csv(path)
        df.columns = [c.strip().lower() for c in df.columns]
        time_col = next((c for c in ("time", "date", "datetime", "timestamp") if c in df.columns), None)
        if time_col:
            df[time_col] = pd.to_datetime(df[time_col])
            df = df.set_index(time_col).sort_index()
        if "spread" not in df.columns:
            df["spread"] = 0.0
        if "tick_volume" not in df.columns:
            df["tick_volume"] = df.get("volume", 0.0)
        return df[[c for c in OHLCV_COLUMNS if c in df.columns]].astype(float).iloc[-count:]

    def get_tick(self, symbol: str) -> dict:
        df = self.get_rates(self.cfg.setup_timeframe, 1)
        bid = float(df["close"].iloc[-1])
        spread_points = float(df["spread"].iloc[-1]) if "spread" in df else 0.0
        return {"bid": bid, "ask": bid + spread_points * self.cfg.point, "spread_points": spread_points, "time": None}

    def symbol_info(self, symbol: str) -> dict:
        preset = self.cfg.symbol_preset()
        return {
            "point": self.cfg.point,
            "digits": self.cfg.digits,
            "volume_min": self.cfg.min_lot,
            "volume_max": self.cfg.max_lot,
            "volume_step": self.cfg.lot_step,
            "trade_contract_size": preset.get("contract_size", 1.0),
            "trade_mode": 4,
        }

    def account_info(self) -> dict:
        return {
            "balance": self._balance,
            "equity": self._balance,
            "margin_free": self._balance,
            "margin_level": 0.0,
            "currency": "USD",
            "trade_allowed": True,
        }


def make_connector(cfg: Config, **kwargs) -> BaseConnector:
    source = (cfg.data_source or "mt5").lower()
    if source == "mt5":
        return MT5Connector(cfg)
    if source == "synthetic":
        return SyntheticConnector(cfg, **kwargs)
    if source == "csv":
        return CSVConnector(cfg, **kwargs)
    raise ValueError(f"Unknown data_source: {cfg.data_source}")
