from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR
from typing import Any

from .base import Broker, OrderResult
from ..domain import OrderRequest, Quote, Side


class MT5Unavailable(RuntimeError):
    pass


class MT5Broker(Broker):
    """Live MetaTrader 5 adapter with market-data and risk-sizing helpers."""

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
                "MetaTrader5 is not installed. On Windows run: pip install -e '.[live]'"
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

    def symbol_details(self, symbol: str) -> dict[str, float]:
        self.connect()
        info = self._ensure_symbol(symbol)
        return {
            "point": float(info.point),
            "digits": float(info.digits),
            "volume_min": float(info.volume_min),
            "volume_max": float(info.volume_max),
            "volume_step": float(info.volume_step),
        }

    def volume_constraints(self, symbol: str) -> dict[str, float]:
        details = self.symbol_details(symbol)
        return {
            "min": details["volume_min"],
            "max": details["volume_max"],
            "step": details["volume_step"],
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
        steps = ((value - minimum) / step).quantize(
            Decimal("1"), rounding=ROUND_FLOOR
        )
        normalized = minimum + steps * step
        if abs(float(normalized) - lots) > 1e-9:
            raise ValueError(f"volume must follow broker step {c['step']} lots")

    def loss_at_stop(
        self,
        symbol: str,
        side: Side,
        lots: float,
        entry: float,
        stop: float,
    ) -> float:
        self.connect()
        self.validate_volume(symbol, lots)
        mt5 = self._module()
        order_type = mt5.ORDER_TYPE_BUY if side is Side.BUY else mt5.ORDER_TYPE_SELL
        result = mt5.order_calc_profit(order_type, symbol, lots, entry, stop)
        if result is None:
            raise ValueError(f"unable to calculate stop loss: {mt5.last_error()}")
        return abs(float(result))

    def size_for_risk(
        self,
        *,
        symbol: str,
        side: Side,
        entry: float,
        stop: float,
        max_risk_cash: float,
    ) -> float | None:
        if max_risk_cash <= 0:
            return None
        self.connect()
        mt5 = self._module()
        constraints = self.volume_constraints(symbol)
        order_type = mt5.ORDER_TYPE_BUY if side is Side.BUY else mt5.ORDER_TYPE_SELL
        loss_one = mt5.order_calc_profit(order_type, symbol, 1.0, entry, stop)
        if loss_one is None or abs(float(loss_one)) <= 0:
            raise ValueError(f"unable to size risk: {mt5.last_error()}")
        raw = max_risk_cash / abs(float(loss_one))
        if raw < constraints["min"]:
            return None
        capped = min(raw, constraints["max"])
        minimum = Decimal(str(constraints["min"]))
        step = Decimal(str(constraints["step"]))
        value = Decimal(str(capped))
        steps = ((value - minimum) / step).quantize(
            Decimal("1"), rounding=ROUND_FLOOR
        )
        normalized = minimum + steps * step
        lots = float(normalized)
        if lots < constraints["min"]:
            return None
        self.validate_volume(symbol, lots)
        if self.loss_at_stop(symbol, side, lots, entry, stop) > max_risk_cash + 1e-9:
            return None
        return lots

    def _timeframe(self, name: str) -> Any:
        mt5 = self._module()
        mapping = {
            "M1": mt5.TIMEFRAME_M1,
            "M2": mt5.TIMEFRAME_M2,
            "M3": mt5.TIMEFRAME_M3,
            "M5": mt5.TIMEFRAME_M5,
            "M10": mt5.TIMEFRAME_M10,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H2": mt5.TIMEFRAME_H2,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }
        key = name.strip().upper()
        if key not in mapping:
            raise ValueError(f"unsupported MT5 timeframe: {name}")
        return mapping[key]

    def rates(self, symbol: str, timeframe: str = "M5", count: int = 220) -> list[dict[str, Any]]:
        self.connect()
        self._ensure_symbol(symbol)
        mt5 = self._module()
        rows = mt5.copy_rates_from_pos(
            symbol,
            self._timeframe(timeframe),
            0,
            max(2, int(count)),
        )
        if rows is None:
            raise ValueError(f"unable to fetch MT5 rates for {symbol}: {mt5.last_error()}")
        return [
            {
                "time": datetime.fromtimestamp(float(row["time"]), tz=timezone.utc).isoformat(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "tick_volume": int(row["tick_volume"]),
            }
            for row in rows
        ]

    def positions(self) -> list[dict[str, Any]]:
        self.connect()
        mt5 = self._module()
        rows = mt5.positions_get() or ()
        result = []
        for row in rows:
            side = Side.BUY if int(row.type) == int(mt5.POSITION_TYPE_BUY) else Side.SELL
            result.append(
                {
                    "ticket": str(row.ticket),
                    "symbol": str(row.symbol),
                    "side": side,
                    "volume": float(row.volume),
                    "price_open": float(row.price_open),
                    "sl": float(row.sl),
                    "tp": float(row.tp),
                    "profit": float(row.profit),
                }
            )
        return result

    def deals_since(self, hours: int = 72) -> list[dict[str, Any]]:
        self.connect()
        mt5 = self._module()
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=max(1, hours))
        rows = mt5.history_deals_get(start, end) or ()
        deals = []
        for row in rows:
            if int(getattr(row, "magic", 0)) != self.magic:
                continue
            side = "buy" if int(row.type) == int(mt5.DEAL_TYPE_BUY) else "sell"
            if int(row.entry) == int(mt5.DEAL_ENTRY_OUT):
                entry_type = "out"
            elif int(row.entry) == int(mt5.DEAL_ENTRY_IN):
                entry_type = "in"
            else:
                entry_type = str(int(row.entry))
            deals.append(
                {
                    "ticket": str(row.ticket),
                    "position_id": str(row.position_id),
                    "symbol": str(row.symbol),
                    "side": side,
                    "entry_type": entry_type,
                    "volume": float(row.volume),
                    "price": float(row.price),
                    "profit": float(row.profit),
                    "commission": float(row.commission),
                    "swap": float(row.swap),
                    "occurred_at": datetime.fromtimestamp(
                        float(row.time), tz=timezone.utc
                    ).isoformat(),
                }
            )
        return deals

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
