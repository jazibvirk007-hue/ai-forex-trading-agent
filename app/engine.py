from __future__ import annotations

import asyncio
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .agents.orchestrator import AgentConsensus, MultiAgentOrchestrator
from .brokers.mt5 import MT5Broker
from .config import Settings
from .domain import OrderRequest, Side
from .integrations.ai import AIProviderClient
from .portfolio import CorrelationGuard, Exposure, close_returns
from .research import RSSResearchProvider
from .risk import RiskEngine, RiskLimits
from .storage import TradingStore
from .strategies.registry import MarketSeries, StrategyCandidate, StrategyRegistry


class EngineNotConfigured(RuntimeError):
    pass


class AutonomousTradingEngine:
    """Single-process autonomous live engine for the local Windows workstation.

    The AI debate may approve or reject a deterministic strategy candidate, but
    position size and final execution constraints remain in code.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = TradingStore(settings.database_url)
        self.registry = StrategyRegistry()
        self.risk = RiskEngine(
            RiskLimits(
                risk_per_trade=settings.risk_per_trade,
                max_daily_loss=settings.max_daily_loss,
                max_weekly_loss=settings.max_weekly_loss,
                max_drawdown=settings.max_drawdown,
                max_open_positions=settings.max_open_positions,
                max_correlated_positions=settings.max_correlated_positions,
            )
        )
        self.correlation = CorrelationGuard(settings.correlation_threshold)
        feeds = [item.strip() for item in settings.research_feed_urls.split(",") if item.strip()]
        self.research = RSSResearchProvider(feeds)
        self.ai_client = AIProviderClient()
        self._orchestrator: MultiAgentOrchestrator | None = None
        self._ai_provider: str | None = None
        self._ai_model: str | None = None
        self._ai_base_url: str | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._cycle_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._running = False
        self._last_cycle_at: str | None = None
        self._last_cycle_summary: dict[str, Any] = {}
        self._last_error: str | None = None

        if settings.ai_api_key and settings.ai_model:
            self.configure_ai(
                provider=settings.ai_provider,
                model=settings.ai_model,
                api_key=settings.ai_api_key,
                base_url=settings.ai_base_url,
            )

    def broker(self) -> MT5Broker:
        return MT5Broker(
            terminal_path=self.settings.mt5_terminal_path,
            login=self.settings.mt5_login,
            password=self.settings.mt5_password,
            server=self.settings.mt5_server,
            deviation=self.settings.mt5_deviation,
            magic=self.settings.mt5_magic,
        )

    def configure_ai(
        self, provider: str, model: str, api_key: str, base_url: str | None = None
    ) -> None:
        if not provider.strip() or not model.strip() or not api_key.strip():
            raise EngineNotConfigured("provider, model and API key are required")
        self._orchestrator = MultiAgentOrchestrator(
            self.ai_client,
            provider=provider.strip(),
            model=model.strip(),
            api_key=api_key.strip(),
            base_url=base_url.strip() if base_url else None,
        )
        self._ai_provider = provider.strip()
        self._ai_model = model.strip()
        self._ai_base_url = base_url.strip() if base_url else None
        self.store.event("ai_configured", f"Autonomous AI configured: {provider}/{model}")

    def ai_configured(self) -> bool:
        return self._orchestrator is not None

    def status(self) -> dict[str, Any]:
        with self._state_lock:
            return {
                "running": self._running,
                "last_cycle_at": self._last_cycle_at,
                "last_error": self._last_error,
                "last_cycle": self._last_cycle_summary,
                "kill_switch": self.store.kill_switch(),
                "autonomous_execution_enabled": self.settings.autonomous_execution_enabled,
                "live_enabled": self.settings.allow_live_trading,
                "live_armed": self.settings.live_trading_armed,
                "ai_configured": self.ai_configured(),
                "ai_provider": self._ai_provider,
                "ai_model": self._ai_model,
                "symbols": self.symbols(),
                "timeframe": self.settings.engine_timeframe,
                "cycle_seconds": self.settings.engine_cycle_seconds,
                "strategies": self.registry.names(),
                "risk_state": self.store.risk_snapshot(),
            }

    def symbols(self) -> list[str]:
        return [
            item.strip()
            for item in self.settings.engine_symbols.split(",")
            if item.strip()
        ]

    def start(self) -> None:
        with self._state_lock:
            if self._running:
                return
            if self.settings.require_ai_consensus and not self.ai_configured():
                raise EngineNotConfigured(
                    "configure an AI provider/model before starting the autonomous engine"
                )
            self._stop.clear()
            self._running = True
            self._last_error = None
            self._thread = threading.Thread(
                target=self._loop,
                name="tj-trading-engine",
                daemon=True,
            )
            self._thread.start()
        self.store.event("engine_started", "Autonomous market engine started")

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        with self._state_lock:
            self._running = False
        self.store.event("engine_stopped", "Autonomous market engine stopped")

    def emergency_stop(self) -> None:
        self.store.set_kill_switch(True)
        self.stop()
        self.store.event(
            "kill_switch",
            "Emergency kill switch enabled. No new live orders are permitted.",
            level="warning",
        )

    def resume_from_kill_switch(self) -> None:
        self.store.set_kill_switch(False)
        self.store.event("kill_switch_reset", "Emergency kill switch reset")

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:  # noqa: BLE001
                with self._state_lock:
                    self._last_error = str(exc)
                self.store.event("cycle_error", str(exc), level="error")
            self._stop.wait(max(5, self.settings.engine_cycle_seconds))
        with self._state_lock:
            self._running = False

    def _market_series(self, broker: MT5Broker, symbol: str) -> MarketSeries:
        rates = broker.rates(
            symbol,
            timeframe=self.settings.engine_timeframe,
            count=self.settings.engine_bars,
        )
        if len(rates) < 40:
            raise ValueError(f"{symbol}: insufficient live bars ({len(rates)})")
        quote = broker.quote(symbol)
        return MarketSeries(
            symbol=symbol,
            closes=tuple(float(row["close"]) for row in rates),
            highs=tuple(float(row["high"]) for row in rates),
            lows=tuple(float(row["low"]) for row in rates),
            spread=quote.spread,
        )

    def _correlated_positions(
        self,
        broker: MT5Broker,
        candidate: StrategyCandidate,
        market: MarketSeries,
    ) -> tuple[int, tuple[str, ...]]:
        exposures: list[Exposure] = []
        for position in broker.positions():
            symbol = str(position["symbol"])
            if symbol == candidate.symbol:
                exposures.append(
                    Exposure(symbol, position["side"], close_returns(market.closes))
                )
                continue
            try:
                rates = broker.rates(
                    symbol,
                    timeframe=self.settings.engine_timeframe,
                    count=min(self.settings.engine_bars, 160),
                )
            except (ValueError, RuntimeError):
                continue
            exposures.append(
                Exposure(
                    symbol,
                    position["side"],
                    close_returns([float(row["close"]) for row in rates]),
                )
            )
        result = self.correlation.compare(
            candidate.side,
            close_returns(market.closes),
            exposures,
        )
        return result.correlated_positions, result.blockers

    async def _consensus(
        self, candidate: StrategyCandidate
    ) -> tuple[AgentConsensus, int]:
        research = await self.research.fetch(candidate.symbol)
        if self._orchestrator is None:
            if self.settings.require_ai_consensus:
                raise EngineNotConfigured("AI consensus is required but not configured")
            return (
                AgentConsensus(
                    candidate.side.value,
                    candidate.confidence,
                    "Technical-only fallback because AI consensus is disabled.",
                    {},
                ),
                len(research.items),
            )
        consensus = await self._orchestrator.analyze(candidate, research)
        return consensus, len(research.items)

    def _cooldown_active(self, symbol: str) -> bool:
        last = self.store.last_trade_time(symbol)
        if last is None:
            return False
        age = (datetime.now(timezone.utc) - last).total_seconds()
        return age < self.settings.min_seconds_between_trades

    def _process_symbol(
        self, broker: MT5Broker, status: dict[str, Any], symbol: str
    ) -> dict[str, Any]:
        market = self._market_series(broker, symbol)
        candidates = self.registry.evaluate(market)
        if not candidates:
            self.store.event("no_signal", "No deterministic strategy candidate", symbol=symbol)
            return {"symbol": symbol, "result": "no_signal"}

        candidate = candidates[0]
        if self._cooldown_active(symbol):
            self.store.event("cooldown", "Trade cooldown active", symbol=symbol)
            return {"symbol": symbol, "result": "cooldown"}

        consensus, headline_count = asyncio.run(self._consensus(candidate))
        if consensus.side is None:
            self.store.event(
                "ai_skip",
                consensus.rationale,
                symbol=symbol,
                payload={"confidence": consensus.confidence},
            )
            return {"symbol": symbol, "result": "ai_skip", "confidence": consensus.confidence}
        if consensus.side is not candidate.side:
            self.store.event(
                "debate_conflict",
                "AI direction conflicts with deterministic strategy",
                symbol=symbol,
                payload={
                    "strategy_side": candidate.side.value,
                    "ai_side": consensus.side.value,
                    "ai_confidence": consensus.confidence,
                },
            )
            return {"symbol": symbol, "result": "debate_conflict"}
        if consensus.confidence < self.settings.min_ai_confidence:
            self.store.event(
                "low_ai_confidence",
                f"AI confidence {consensus.confidence:.2f} below threshold",
                symbol=symbol,
            )
            return {"symbol": symbol, "result": "low_ai_confidence"}

        correlated, blockers = self._correlated_positions(
            broker, candidate, market
        )
        account = self.store.account_state(
            equity=float(status["equity"]),
            open_positions=int(status["positions"]),
            correlated_positions=correlated,
        )
        limits = self.risk.account_limits(account)
        if not limits.approved:
            self.store.event(
                "risk_block",
                limits.reason,
                symbol=symbol,
                level="warning",
                payload={"correlation_blockers": blockers},
            )
            return {"symbol": symbol, "result": "risk_block", "reason": limits.reason}

        quote = broker.quote(symbol)
        entry = quote.ask if candidate.side is Side.BUY else quote.bid
        if candidate.side is Side.BUY:
            stop = entry - candidate.stop_distance
            target = entry + candidate.target_distance
        else:
            stop = entry + candidate.stop_distance
            target = entry - candidate.target_distance

        risk_cash = float(status["equity"]) * self.settings.risk_per_trade
        volume = broker.size_for_risk(
            symbol=symbol,
            side=candidate.side,
            entry=entry,
            stop=stop,
            max_risk_cash=risk_cash,
        )
        if volume is None:
            self.store.event(
                "minimum_lot_too_large",
                "Broker minimum volume exceeds the configured cash risk at the stop",
                symbol=symbol,
                level="warning",
            )
            return {"symbol": symbol, "result": "minimum_lot_too_large"}

        estimated_loss = broker.loss_at_stop(
            symbol, candidate.side, volume, entry, stop
        )
        combined_confidence = min(
            0.99, (candidate.confidence + consensus.confidence) / 2.0
        )
        proposal = {
            "symbol": symbol,
            "side": candidate.side.value,
            "volume_lots": volume,
            "entry": entry,
            "stop_loss": stop,
            "take_profit": target,
            "estimated_stop_loss_cash": estimated_loss,
            "strategy": candidate.strategy,
            "technical_confidence": candidate.confidence,
            "ai_confidence": consensus.confidence,
            "headline_count": headline_count,
            "rationale": consensus.rationale,
        }

        if self.store.kill_switch():
            self.store.event(
                "kill_switch_block",
                "Kill switch is enabled",
                symbol=symbol,
                level="warning",
                payload=proposal,
            )
            return {"symbol": symbol, "result": "kill_switch", "proposal": proposal}

        live_ready = (
            self.settings.autonomous_execution_enabled
            and self.settings.allow_live_trading
            and self.settings.live_trading_armed
            and self.settings.broker_mode.lower() == "live"
        )
        if not live_ready:
            self.store.event(
                "live_locked_candidate",
                "Qualified live candidate found; execution lock remains enabled",
                symbol=symbol,
                payload=proposal,
            )
            return {"symbol": symbol, "result": "live_locked", "proposal": proposal}

        order = OrderRequest(
            symbol=symbol,
            side=candidate.side,
            units=volume,
            entry_price=entry,
            stop_loss=stop,
            take_profit=target,
        )
        result = broker.submit(order)
        if not result.accepted:
            self.store.event(
                "order_rejected",
                result.message,
                symbol=symbol,
                level="error",
                payload=proposal,
            )
            return {"symbol": symbol, "result": "order_rejected", "message": result.message}

        self.store.record_trade(
            symbol=symbol,
            side=candidate.side.value,
            order_id=result.order_id,
            volume_lots=volume,
            entry_price=entry,
            stop_loss=stop,
            take_profit=target,
            risk_cash=estimated_loss,
            strategy=candidate.strategy,
            confidence=combined_confidence,
            rationale=consensus.rationale,
        )
        self.store.event(
            "live_order_submitted",
            result.message,
            symbol=symbol,
            payload={**proposal, "order_id": result.order_id},
        )
        return {
            "symbol": symbol,
            "result": "submitted",
            "order_id": result.order_id,
            "proposal": proposal,
        }

    def _sync_deals(self, broker: MT5Broker) -> int:
        new_count = 0
        for deal in broker.deals_since(hours=self.settings.deal_sync_hours):
            if not self.store.upsert_deal(deal):
                continue
            new_count += 1
            if (
                deal.get("entry_type") == "out"
                and self.settings.reflection_enabled
                and self._orchestrator is not None
            ):
                try:
                    reflection = asyncio.run(self._orchestrator.reflect(deal))
                    self.store.record_reflection(
                        str(deal["ticket"]),
                        str(deal.get("symbol") or ""),
                        float(deal.get("profit") or 0.0),
                        reflection,
                    )
                except Exception as exc:  # noqa: BLE001
                    self.store.event(
                        "reflection_error",
                        str(exc),
                        symbol=str(deal.get("symbol") or ""),
                        level="error",
                    )
        return new_count

    def run_once(self) -> dict[str, Any]:
        if not self._cycle_lock.acquire(blocking=False):
            raise RuntimeError("an engine cycle is already running")
        broker = self.broker()
        started = datetime.now(timezone.utc)
        try:
            if self.store.kill_switch():
                summary = {"result": "kill_switch", "symbols": []}
                return summary

            status = broker.status()
            if not status["trade_allowed"] and self.settings.autonomous_execution_enabled:
                raise RuntimeError("MT5 terminal reports that trading is not allowed")

            self.store.account_state(
                equity=float(status["equity"]),
                open_positions=int(status["positions"]),
            )
            new_deals = self._sync_deals(broker)
            outcomes = []
            for symbol in self.symbols():
                if int(status["positions"]) >= self.settings.max_open_positions:
                    outcomes.append({"symbol": symbol, "result": "position_limit"})
                    break
                try:
                    outcome = self._process_symbol(broker, status, symbol)
                except Exception as exc:  # noqa: BLE001
                    self.store.event(
                        "symbol_error",
                        str(exc),
                        symbol=symbol,
                        level="error",
                    )
                    outcome = {"symbol": symbol, "result": "error", "error": str(exc)}
                outcomes.append(outcome)
                if outcome.get("result") == "submitted":
                    status = broker.status()

            summary = {
                "result": "completed",
                "started_at": started.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "new_deals_synced": new_deals,
                "symbols": outcomes,
            }
            self.store.event("cycle_complete", "Autonomous scan cycle completed", payload=summary)
            with self._state_lock:
                self._last_cycle_at = summary["finished_at"]
                self._last_cycle_summary = summary
                self._last_error = None
            return summary
        finally:
            broker.close()
            self._cycle_lock.release()
