"""
MetaTrader 5 connector for JustMarkets (or any MT5 broker).

IMPORTANT: the `MetaTrader5` package only runs on WINDOWS. This module is
import-guarded so the rest of the codebase (risk engine, strategies, backtests)
still imports fine on Linux/Mac for development and testing. The connector
methods raise a clear error if MetaTrader5 is unavailable.

This layer is pure I/O: connect, read account/symbol/candles, send/manage
orders. All strategy and risk logic lives elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from ..risk.position_sizing import SymbolSpec

try:  # Windows only
    import MetaTrader5 as mt5  # type: ignore
    _MT5_AVAILABLE = True
except Exception:  # pragma: no cover - not importable off Windows
    mt5 = None  # type: ignore
    _MT5_AVAILABLE = False


# Map our timeframe strings to MT5 constants (resolved lazily so import is safe).
def _tf_const(timeframe: str) -> int:
    if not _MT5_AVAILABLE:
        raise RuntimeError("MetaTrader5 is not available on this machine.")
    table = {
        "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    if timeframe not in table:
        raise ValueError(f"Unsupported timeframe {timeframe!r}. Use {list(table)}.")
    return table[timeframe]


@dataclass
class AccountState:
    login: int
    balance: float
    equity: float
    margin_free: float
    currency: str
    leverage: int


@dataclass
class OpenPosition:
    ticket: int
    symbol: str
    side: int          # +1 long, -1 short
    volume: float
    price_open: float
    sl: float
    tp: float
    profit: float
    magic: int
    comment: str


class MT5Connector:
    """Thin wrapper over the MetaTrader5 API."""

    def __init__(self, magic: int = 990011):
        self.magic = magic
        self._connected = False

    # ----- lifecycle -----
    @staticmethod
    def available() -> bool:
        return _MT5_AVAILABLE

    def connect(
        self,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        path: Optional[str] = None,
    ) -> AccountState:
        """
        Connect to the running/installed MT5 terminal.

        If login/password/server are omitted, MT5 uses the account already
        logged into the terminal (recommended for demo).
        """
        if not _MT5_AVAILABLE:
            raise RuntimeError(
                "MetaTrader5 package not available. Install it on Windows: "
                "pip install MetaTrader5"
            )
        kwargs = {}
        if path:
            kwargs["path"] = path
        if login and password and server:
            kwargs.update(login=int(login), password=password, server=server)

        if not mt5.initialize(**kwargs):
            code, msg = mt5.last_error()
            raise ConnectionError(f"MT5 initialize failed ({code}): {msg}")

        self._connected = True
        return self.account_info()

    def shutdown(self) -> None:
        if _MT5_AVAILABLE and self._connected:
            mt5.shutdown()
            self._connected = False

    # ----- account / symbols -----
    def account_info(self) -> AccountState:
        info = mt5.account_info()
        if info is None:
            raise ConnectionError(f"account_info failed: {mt5.last_error()}")
        return AccountState(
            login=info.login,
            balance=info.balance,
            equity=info.equity,
            margin_free=info.margin_free,
            currency=info.currency,
            leverage=info.leverage,
        )

    def list_symbols(self, contains: str = "") -> list[str]:
        """All symbols whose name contains `contains` (case-insensitive)."""
        symbols = mt5.symbols_get()
        if symbols is None:
            return []
        c = contains.upper()
        return [s.name for s in symbols if c in s.name.upper()]

    def ensure_symbol(self, symbol: str) -> None:
        """Make sure the symbol is selected in Market Watch."""
        if not mt5.symbol_select(symbol, True):
            raise ValueError(f"Could not select symbol {symbol!r}: {mt5.last_error()}")

    def symbol_spec(self, symbol: str) -> SymbolSpec:
        """Build the risk-engine SymbolSpec from the broker's real contract rules."""
        self.ensure_symbol(symbol)
        info = mt5.symbol_info(symbol)
        if info is None:
            raise ValueError(f"symbol_info failed for {symbol!r}: {mt5.last_error()}")
        # trade_tick_size / trade_tick_value describe money-per-tick per 1.0 lot.
        tick_size = info.trade_tick_size or info.point
        tick_value = info.trade_tick_value
        return SymbolSpec(
            tick_size=tick_size,
            tick_value=tick_value,
            volume_min=info.volume_min,
            volume_step=info.volume_step,
            volume_max=info.volume_max,
        )

    def symbol_details(self, symbol: str) -> dict:
        """Human-friendly dump of a symbol's key trading attributes."""
        self.ensure_symbol(symbol)
        i = mt5.symbol_info(symbol)
        if i is None:
            raise ValueError(f"symbol_info failed for {symbol!r}")
        return {
            "name": i.name,
            "description": i.description,
            "digits": i.digits,
            "point": i.point,
            "trade_tick_size": i.trade_tick_size,
            "trade_tick_value": i.trade_tick_value,
            "trade_contract_size": i.trade_contract_size,
            "volume_min": i.volume_min,
            "volume_step": i.volume_step,
            "volume_max": i.volume_max,
            "spread": i.spread,
            "trade_stops_level": i.trade_stops_level,
        }

    # ----- market data -----
    def get_candles(self, symbol: str, timeframe: str, count: int = 500) -> pd.DataFrame:
        """
        Fetch the most recent `count` candles as a DataFrame with columns
        open/high/low/close/volume, indexed by UTC timestamp (oldest -> newest),
        matching the format used by our backtester.

        NOTE: MT5 timestamps are in the broker's server time. We label them UTC;
        for daily/weekly HTF resampling this can shift day boundaries slightly.
        Documented in WINDOWS_SETUP.md - fine for H4 swing but be aware.
        """
        self.ensure_symbol(symbol)
        rates = mt5.copy_rates_from_pos(symbol, _tf_const(timeframe), 0, count)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"No candles for {symbol} {timeframe}: {mt5.last_error()}")
        df = pd.DataFrame(rates)
        df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.rename(columns={"tick_volume": "volume"})
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        return df.set_index("timestamp")

    def current_tick(self, symbol: str) -> tuple[float, float]:
        """Return (bid, ask) for the symbol."""
        self.ensure_symbol(symbol)
        t = mt5.symbol_info_tick(symbol)
        if t is None:
            raise RuntimeError(f"No tick for {symbol}: {mt5.last_error()}")
        return t.bid, t.ask

    # ----- positions -----
    def get_open_positions(self, symbol: Optional[str] = None) -> list[OpenPosition]:
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if positions is None:
            return []
        out = []
        for p in positions:
            out.append(
                OpenPosition(
                    ticket=p.ticket,
                    symbol=p.symbol,
                    side=1 if p.type == mt5.POSITION_TYPE_BUY else -1,
                    volume=p.volume,
                    price_open=p.price_open,
                    sl=p.sl,
                    tp=p.tp,
                    profit=p.profit,
                    magic=p.magic,
                    comment=p.comment,
                )
            )
        return out

    def bot_positions(self, symbol: Optional[str] = None) -> list[OpenPosition]:
        """Only positions opened by THIS bot (matched by magic number)."""
        return [p for p in self.get_open_positions(symbol) if p.magic == self.magic]

    def closed_deals(self, days: int = 30) -> list[dict]:
        """
        Realized closing deals for THIS bot over the last `days` (source of truth
        for live P&L). Returns dicts with symbol, profit, volume, price, time.
        """
        from datetime import datetime, timedelta
        now = datetime.now()
        deals = mt5.history_deals_get(now - timedelta(days=days), now)
        if deals is None:
            return []
        out = []
        for d in deals:
            # DEAL_ENTRY_OUT deals carry the realized profit of a closed position.
            if d.magic == self.magic and d.entry == mt5.DEAL_ENTRY_OUT:
                out.append({
                    "time": pd.to_datetime(d.time, unit="s", utc=True),
                    "symbol": d.symbol,
                    "volume": d.volume,
                    "price": d.price,
                    "profit": d.profit,
                    "commission": getattr(d, "commission", 0.0),
                    "swap": getattr(d, "swap", 0.0),
                    "comment": d.comment,
                })
        return out

    # ----- orders -----
    def _filling_mode(self, symbol: str) -> int:
        """Pick a supported order-filling mode for the symbol."""
        info = mt5.symbol_info(symbol)
        mode = getattr(info, "filling_mode", 0)
        # filling_mode is a bitmask; prefer IOC, then FOK, then RETURN.
        if mode & 2:
            return mt5.ORDER_FILLING_IOC
        if mode & 1:
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN

    def place_market_order(
        self,
        symbol: str,
        side: int,
        volume: float,
        sl_price: float,
        tp_price: float,
        deviation: int = 20,
        comment: str = "bot",
    ) -> dict:
        """
        Send a market order with attached stop-loss and take-profit.
        `side`: +1 buy, -1 sell. Prices are rounded to the symbol's digits.
        Returns a result dict (retcode, order ticket, etc.).
        """
        self.ensure_symbol(symbol)
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        price = tick.ask if side == 1 else tick.bid
        order_type = mt5.ORDER_TYPE_BUY if side == 1 else mt5.ORDER_TYPE_SELL

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": price,
            "sl": round(sl_price, info.digits),
            "tp": round(tp_price, info.digits),
            "deviation": deviation,
            "magic": self.magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode(symbol),
        }
        result = mt5.order_send(request)
        return self._result_to_dict(result)

    def close_position(self, position: OpenPosition, deviation: int = 20) -> dict:
        """Close an open position with an opposite market order."""
        self.ensure_symbol(position.symbol)
        tick = mt5.symbol_info_tick(position.symbol)
        # To close a BUY we SELL at bid; to close a SELL we BUY at ask.
        if position.side == 1:
            order_type, price = mt5.ORDER_TYPE_SELL, tick.bid
        else:
            order_type, price = mt5.ORDER_TYPE_BUY, tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": order_type,
            "position": position.ticket,
            "price": price,
            "deviation": deviation,
            "magic": self.magic,
            "comment": "bot close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode(position.symbol),
        }
        return self._result_to_dict(mt5.order_send(request))

    @staticmethod
    def _result_to_dict(result) -> dict:
        if result is None:
            return {"ok": False, "retcode": None, "comment": "order_send returned None"}
        return {
            "ok": result.retcode == mt5.TRADE_RETCODE_DONE,
            "retcode": result.retcode,
            "order": getattr(result, "order", None),
            "deal": getattr(result, "deal", None),
            "price": getattr(result, "price", None),
            "comment": result.comment,
        }
