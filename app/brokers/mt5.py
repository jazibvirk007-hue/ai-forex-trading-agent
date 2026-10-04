from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from typing import Any

from .base import Broker, OrderResult
from ..domain import OrderRequest, Quote, Side


class MT5Unavailable(RuntimeError):
    pass


class MT5Broker(Broker):
    """Live MetaTrader 5 adapter.

    The adapter imports MetaTrader5 lazily because the official package is
    Windows-only. OrderRequest.units is interpreted as MT5 volume in lots.
    """

    def __init__(
        self,
        terminal_path: str | None = None,
        login: int | None = None,
        password: str | None = None,
        server: str | None = None,
        deviation: int = 15,
        magic: int = 560001,
    ) -> None:
        self.terminal_path = terminal_path
        self.login = login
        self.password = password
        self.server = server
        self.deviation = deviation
        self.magic = magic
        self._mt5: Any | None = None

    def _module(self) -> Any:
        if self._mt5 is not None:
            return self._mt5
        try:
            import MetaTrader5 as mt5  # type: ignore
        except ImportError as exc:
            raise MT5Unavailable(
                "MetaTrader5 package is not installed. On Windows run: "
                "pip install -e '.[live]'"
            ) from exc
        self._mt5 = mt5
        return mt5

    def connect(self) -> None:
        mt5 = self._module()
        kwargs: dict[str, Any] = {}
        if self.terminal_path:
            kwargs["path"] = self.terminal_path
        if self.login:
            kwargs["login"] = self.login
        if self.password:
            kwargs["password"] = self.password
        if self.server:
            kwargs["server"] = self.server
        if not mt5.initialize(**kwargs):
            raise MT5Unavailable(f"MT5 initialize failed: {mt5.last_error()}")

    def close(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()

    def _ensure_symbol(self, symbol: str) -> Any:
        mt5 = self._module()
        info = mt5.symbol_info(symbol)
        if info is None:
            raise ValueError(f"MT5 symbol not found: {symbol}")
        if not info.visible and not mt5.symbol_select(symbol, True):
            raise ValueError(f"MT5 symbol could not be selected: {symbol}")
        return info

    def status(self) -> dict[str, Any]:
        self.connect()
        mt5 = self._module()
        account = mt5.account_info()
        terminal = mt5.terminal_info()
        if account is None:
            raise MT5Unavailable(f"MT5 account unavailable: {mt5.last_error()}")
        return {
            "connected": True,
            "login": int(account.login),
            "server": str(account.server),
            "currency": str(account.currency),
            "balance": float(account.balance),
            "equity": float(account.equity),
            "margin_free": float(account.margin_free),
            "profit": float(account.profit),
            "positions": int(mt5.positions_total() or 0),
            "trade_allowed": bool(getattr(terminal, "trade_allowed", False)),
        }

    def quote(self, symbol: str) -> Quote:
        self.connect()
        self._ensure_symbol(symbol)
        mt5 = self._module()
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise ValueError(f"no live MT5 quote for {symbol}")
        return Quote(
            symbol=symbol,
            timestamp=datetime.fromtimestamp(float(tick.time), tz=timezone.utc),
            bid=float(tick.bid),
            ask=float(tick.ask),
        )

    def volume_constraints(self, symbol: str) -> dict[str, float]:
        self.connect()
        info = self._ensure_symbol(symbol)
        return {
            "min": float(info.volume_min),
            "max": float(info.volume_max),
            "step": float(info.volume_step),
        }

    def validate_volume(self, symbol: str, lots: float) -> None:
        c = self.volume_constraints(symbol)
        if lots < c["min"] or lots > c["max"]:
            raise ValueError(
                f"volume {lots} outside broker range {c['min']}..{c['max']} lots"
            )
        step = Decimal(str(c["step"]))
        minimum = Decimal(str(c["min"]))
        value = Decimal(str(lots))
        steps = ((value - minimum) / step).quantize(Decimal("1"), rounding=ROUND_FLOOR)
        normalized = minimum + steps * step
        if abs(float(normalized) - lots) > 1e-9:
            raise ValueError(f"volume must follow broker step {c['step']} lots")

    def loss_at_stop(
        self, symbol: str, side: Side, lots: float, entry: float, stop: float
    ) -> float:
        self.connect()
        self.validate_volume(symbol, lots)
        mt5 = self._module()
        order_type = mt5.ORDER_TYPE_BUY if side is Side.BUY else mt5.ORDER_TYPE_SELL
        result = mt5.order_calc_profit(order_type, symbol, lots, entry, stop)
        if result is None:
            raise ValueError(f"unable to calculate stop loss: {mt5.last_error()}")
        return abs(float(result))

    def submit(self, order: OrderRequest) -> OrderResult:
        order.validate()
        self.connect()
        self.validate_volume(order.symbol, order.units)
        mt5 = self._module()
        self._ensure_symbol(order.symbol)
        tick = mt5.symbol_info_tick(order.symbol)
        if tick is None:
            return OrderResult(False, None, "live quote unavailable")

        order_type = mt5.ORDER_TYPE_BUY if order.side is Side.BUY else mt5.ORDER_TYPE_SELL
        price = float(tick.ask if order.side is Side.BUY else tick.bid)
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": order.symbol,
            "volume": float(order.units),
            "type": order_type,
            "price": price,
            "sl": float(order.stop_loss),
            "tp": float(order.take_profit),
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": "TJ Trading OS",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        check = mt5.order_check(request)
        if check is None:
            return OrderResult(False, None, f"MT5 order_check failed: {mt5.last_error()}")
        if int(check.retcode) != 0:
            return OrderResult(False, None, f"MT5 order_check rejected: {check.comment}")

        result = mt5.order_send(request)
        if result is None:
            return OrderResult(False, None, f"MT5 order_send failed: {mt5.last_error()}")
        accepted_codes = {mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED}
        accepted = int(result.retcode) in accepted_codes
        order_id = str(result.order or result.deal) if accepted else None
        return OrderResult(accepted, order_id, str(result.comment))

    def cancel(self, order_id: str) -> bool:
        self.connect()
        mt5 = self._module()
        request = {"action": mt5.TRADE_ACTION_REMOVE, "order": int(order_id)}
        result = mt5.order_send(request)
        return bool(result and int(result.retcode) == mt5.TRADE_RETCODE_DONE)
