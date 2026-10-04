from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .brokers.mt5 import MT5Broker, MT5Unavailable
from .config import settings
from .domain import OrderRequest, Side
from .engine import EngineNotConfigured, LiveAnalysisEngine
from .integrations.ai import AIProviderClient, AIProviderError, public_provider_catalog
from .integrations.fish_audio import FishAudioClient, FishAudioError
from .risk import AccountState, RiskEngine, RiskLimits


ai_client = AIProviderClient()
engine = LiveAnalysisEngine(settings)
risk_engine = RiskEngine(
    RiskLimits(
        risk_per_trade=settings.risk_per_trade,
        max_daily_loss=settings.max_daily_loss,
        max_weekly_loss=settings.max_weekly_loss,
        max_drawdown=settings.max_drawdown,
        max_open_positions=settings.max_open_positions,
        max_correlated_positions=settings.max_correlated_positions,
    )
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.engine_auto_start:
        try:
            engine.start()
        except EngineNotConfigured as exc:
            engine.store.event("engine_autostart_blocked", str(exc), level="warning")
    yield
    engine.stop()


app = FastAPI(title="TJ Trading OS", version="0.3.0", lifespan=lifespan)

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def mt5_broker() -> MT5Broker:
    return engine.broker()


class RiskCheckRequest(BaseModel):
    equity: float = Field(gt=0)
    start_of_day_equity: float = Field(gt=0)
    start_of_week_equity: float = Field(gt=0)
    peak_equity: float = Field(gt=0)
    open_positions: int = Field(ge=0)
    correlated_positions: int = Field(ge=0)
    stop_distance_price: float = Field(gt=0)
    value_per_price_unit: float = Field(gt=0)


class ProviderModelsRequest(BaseModel):
    provider: str
    api_key: str = Field(min_length=1)
    base_url: str | None = None


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)


class ChatRequest(ProviderModelsRequest):
    model: str = Field(min_length=1)
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)


class EngineAIRequest(ProviderModelsRequest):
    model: str = Field(min_length=1)


class FishModelsRequest(BaseModel):
    api_key: str = Field(min_length=1)
    page_size: int = Field(default=50, ge=1, le=100)
    page_number: int = Field(default=1, ge=1)
    self_only: bool = False


class FishTTSRequest(BaseModel):
    api_key: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=10000)
    reference_id: str | None = None
    model: str = "s2.1-pro"
    format: Literal["mp3", "wav", "pcm", "opus"] = "mp3"


class LiveOrderRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    side: Side
    volume_lots: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    index = STATIC_DIR / "index.html"
    if not index.exists():
        return "<h1>TJ Trading OS</h1><p>UI assets are not installed.</p>"
    return index.read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "product": "TJ Trading OS",
        "mode": settings.broker_mode,
        "broker": settings.broker_name,
        "live_enabled": settings.allow_live_trading,
        "live_armed": settings.live_trading_armed,
        "execution_mode": "confirmed-live",
        "risk_per_trade": settings.risk_per_trade,
        "max_open_positions": settings.max_open_positions,
    }


@app.post("/risk/check")
def risk_check(req: RiskCheckRequest) -> dict:
    state = AccountState(
        req.equity,
        req.start_of_day_equity,
        req.start_of_week_equity,
        req.peak_equity,
        req.open_positions,
        req.correlated_positions,
    )
    decision = risk_engine.check(
        state,
        req.stop_distance_price,
        req.value_per_price_unit,
    )
    return {
        "approved": decision.approved,
        "reason": decision.reason,
        "units": decision.units,
    }


@app.get("/ai/providers")
def ai_providers() -> dict:
    return {"providers": public_provider_catalog()}


@app.post("/ai/models/fetch")
async def ai_models(req: ProviderModelsRequest) -> dict:
    try:
        models = await ai_client.fetch_models(req.provider, req.api_key, req.base_url)
        return {"provider": req.provider, "models": models}
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/ai/chat")
async def ai_chat(req: ChatRequest) -> dict:
    try:
        answer = await ai_client.chat(
            provider=req.provider,
            model=req.model,
            api_key=req.api_key,
            base_url=req.base_url,
            messages=[message.model_dump() for message in req.messages],
        )
        return {"message": answer}
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/engine/ai/configure")
def configure_engine_ai(req: EngineAIRequest) -> dict:
    try:
        engine.configure_ai(
            provider=req.provider,
            model=req.model,
            api_key=req.api_key,
            base_url=req.base_url,
        )
        return {"configured": True, "provider": req.provider, "model": req.model}
    except EngineNotConfigured as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/engine/status")
def engine_status() -> dict:
    return engine.status()


@app.post("/engine/start")
def engine_start() -> dict:
    try:
        engine.start()
        return engine.status()
    except EngineNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/engine/stop")
def engine_stop() -> dict:
    engine.stop()
    return engine.status()


@app.post("/engine/run-once")
def engine_run_once() -> dict:
    try:
        return engine.run_once()
    except EngineNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/engine/emergency-stop")
def emergency_stop() -> dict:
    engine.emergency_stop()
    return engine.status()


@app.post("/engine/resume")
def emergency_resume(
    x_engine_confirm: Annotated[str | None, Header()] = None,
) -> dict:
    if x_engine_confirm != "RESUME":
        raise HTTPException(
            status_code=428,
            detail="resetting the kill switch requires X-Engine-Confirm: RESUME",
        )
    engine.resume_from_kill_switch()
    return engine.status()


@app.get("/engine/events")
def engine_events(limit: int = 50) -> dict:
    return {"events": engine.store.recent_events(min(max(limit, 1), 200))}


@app.get("/engine/proposals")
def engine_proposals(limit: int = 25) -> dict:
    return {"proposals": engine.store.recent_proposals(min(max(limit, 1), 100))}


@app.get("/journal/trades")
def journal_trades(limit: int = 50) -> dict:
    return {"trades": engine.store.recent_trades(min(max(limit, 1), 200))}


@app.get("/journal/reflections")
def journal_reflections(limit: int = 25) -> dict:
    return {"reflections": engine.store.recent_reflections(min(max(limit, 1), 100))}


@app.post("/voice/fish/models/fetch")
async def fish_models(req: FishModelsRequest) -> dict:
    try:
        voices = await FishAudioClient(req.api_key).fetch_voice_models(
            page_size=req.page_size,
            page_number=req.page_number,
            self_only=req.self_only,
        )
        return {"models": voices}
    except FishAudioError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/voice/fish/tts")
async def fish_tts(req: FishTTSRequest) -> Response:
    try:
        audio, media_type = await FishAudioClient(req.api_key).tts(
            text=req.text,
            reference_id=req.reference_id,
            model=req.model or settings.fish_audio_model,
            audio_format=req.format,
        )
        return Response(content=audio, media_type=media_type)
    except FishAudioError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/voice/fish/asr")
async def fish_asr(
    audio: Annotated[UploadFile, File()],
    api_key: Annotated[str, Form()],
) -> dict:
    try:
        content = await audio.read()
        if not content:
            raise HTTPException(status_code=400, detail="empty audio upload")
        return await FishAudioClient(api_key).transcribe(
            content,
            filename=audio.filename or "voice.webm",
            content_type=audio.content_type or "audio/webm",
        )
    except FishAudioError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/broker/mt5/status")
def broker_status() -> dict:
    broker = mt5_broker()
    try:
        return broker.status()
    except (MT5Unavailable, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        broker.close()


@app.get("/broker/mt5/symbol/{symbol}")
def broker_symbol(symbol: str) -> dict:
    broker = mt5_broker()
    try:
        quote = broker.quote(symbol)
        constraints = broker.volume_constraints(symbol)
        return {
            "symbol": quote.symbol,
            "bid": quote.bid,
            "ask": quote.ask,
            "spread": quote.spread,
            "timestamp": quote.timestamp.isoformat(),
            "volume": constraints,
        }
    except (MT5Unavailable, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        broker.close()


def _assert_live_execution_allowed() -> None:
    if settings.broker_mode.lower() != "live":
        raise HTTPException(status_code=409, detail="broker mode is not live")
    if not settings.allow_live_trading or not settings.live_trading_armed:
        raise HTTPException(
            status_code=423,
            detail="live execution is locked; enable ALLOW_LIVE_TRADING and LIVE_TRADING_ARMED",
        )
    if engine.store.kill_switch():
        raise HTTPException(status_code=423, detail="emergency kill switch is enabled")


def _execute_checked_order(
    broker: MT5Broker,
    order: OrderRequest,
    *,
    strategy: str,
    confidence: float,
    rationale: str,
) -> dict:
    status = broker.status()
    if not status["trade_allowed"]:
        raise HTTPException(status_code=409, detail="MT5 terminal trading is disabled")
    if status["positions"] >= settings.max_open_positions:
        raise HTTPException(status_code=409, detail="maximum open positions reached")

    broker.validate_volume(order.symbol, order.units)
    current_quote = broker.quote(order.symbol)
    current_entry = current_quote.ask if order.side is Side.BUY else current_quote.bid
    refreshed = OrderRequest(
        symbol=order.symbol,
        side=order.side,
        units=order.units,
        entry_price=current_entry,
        stop_loss=order.stop_loss,
        take_profit=order.take_profit,
    )
    refreshed.validate()

    stop_loss_cash = broker.loss_at_stop(
        refreshed.symbol,
        refreshed.side,
        refreshed.units,
        refreshed.entry_price,
        refreshed.stop_loss,
    )
    max_risk_cash = float(status["equity"]) * settings.risk_per_trade
    if stop_loss_cash > max_risk_cash + 1e-9:
        raise HTTPException(
            status_code=422,
            detail=(
                f"current stop risk is {stop_loss_cash:.2f} {status['currency']}; "
                f"configured maximum is {max_risk_cash:.2f} {status['currency']}"
            ),
        )

    result = broker.submit(refreshed)
    if not result.accepted:
        raise HTTPException(status_code=502, detail=result.message)

    engine.store.record_trade(
        symbol=refreshed.symbol,
        side=refreshed.side.value,
        order_id=result.order_id,
        volume_lots=refreshed.units,
        entry_price=refreshed.entry_price,
        stop_loss=refreshed.stop_loss,
        take_profit=refreshed.take_profit,
        risk_cash=stop_loss_cash,
        strategy=strategy,
        confidence=confidence,
        rationale=rationale,
    )
    return {
        "accepted": True,
        "order_id": result.order_id,
        "message": result.message,
        "entry_price": refreshed.entry_price,
        "estimated_stop_loss_cash": stop_loss_cash,
        "max_risk_cash": max_risk_cash,
    }


@app.post("/engine/proposals/{proposal_id}/execute")
def execute_proposal(
    proposal_id: int,
    x_live_confirm: Annotated[str | None, Header()] = None,
) -> dict:
    _assert_live_execution_allowed()
    expected = f"PROPOSAL:{proposal_id}"
    if x_live_confirm != expected:
        raise HTTPException(
            status_code=428,
            detail=f"this live order requires X-Live-Confirm: {expected}",
        )

    proposal = engine.store.proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    if proposal["status"] != "ready":
        raise HTTPException(status_code=409, detail="proposal is no longer executable")

    created = datetime.fromisoformat(str(proposal["created_at"]))
    age = (datetime.now(timezone.utc) - created).total_seconds()
    if age > settings.max_proposal_age_seconds:
        engine.store.set_proposal_status(proposal_id, "expired")
        raise HTTPException(status_code=409, detail="proposal expired; run a fresh scan")

    side = Side(str(proposal["side"]))
    reference_entry = float(proposal["reference_entry"])
    stop_loss = float(proposal["stop_loss"])
    max_drift = abs(reference_entry - stop_loss) * 0.25

    broker = mt5_broker()
    try:
        quote = broker.quote(str(proposal["symbol"]))
        current_entry = quote.ask if side is Side.BUY else quote.bid
        if abs(current_entry - reference_entry) > max_drift:
            engine.store.set_proposal_status(proposal_id, "stale")
            raise HTTPException(
                status_code=409,
                detail="market moved too far from the analyzed entry; run a fresh scan",
            )

        order = OrderRequest(
            symbol=str(proposal["symbol"]),
            side=side,
            units=float(proposal["volume_lots"]),
            entry_price=current_entry,
            stop_loss=stop_loss,
            take_profit=float(proposal["take_profit"]),
        )
        response = _execute_checked_order(
            broker,
            order,
            strategy=str(proposal["strategy"]),
            confidence=(
                float(proposal["technical_confidence"])
                + float(proposal["ai_confidence"])
            )
            / 2.0,
            rationale=str(proposal["rationale"]),
        )
        engine.store.set_proposal_status(proposal_id, "executed")
        engine.store.event(
            "confirmed_live_execution",
            "User-confirmed proposal sent to MT5",
            symbol=str(proposal["symbol"]),
            payload={"proposal_id": proposal_id, "order_id": response["order_id"]},
        )
        return {**response, "proposal_id": proposal_id}
    finally:
        broker.close()


@app.post("/broker/mt5/order")
def live_order(
    req: LiveOrderRequest,
    x_live_confirm: Annotated[str | None, Header()] = None,
) -> dict:
    _assert_live_execution_allowed()
    if x_live_confirm != "LIVE":
        raise HTTPException(
            status_code=428,
            detail="live order requires X-Live-Confirm: LIVE",
        )

    broker = mt5_broker()
    try:
        quote = broker.quote(req.symbol)
        entry = quote.ask if req.side is Side.BUY else quote.bid
        order = OrderRequest(
            symbol=req.symbol,
            side=req.side,
            units=req.volume_lots,
            entry_price=entry,
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
        )
        return _execute_checked_order(
            broker,
            order,
            strategy="manual",
            confidence=1.0,
            rationale="Explicit user-created live order.",
        )
    except (MT5Unavailable, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        broker.close()
