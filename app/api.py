from fastapi import FastAPI
from pydantic import BaseModel, Field

from .risk import AccountState, RiskEngine

app = FastAPI(title="AI Forex Trading Agent", version="0.1.0")
risk_engine = RiskEngine()


class RiskCheckRequest(BaseModel):
    equity: float = Field(gt=0)
    start_of_day_equity: float = Field(gt=0)
    start_of_week_equity: float = Field(gt=0)
    peak_equity: float = Field(gt=0)
    open_positions: int = Field(ge=0)
    correlated_positions: int = Field(ge=0)
    stop_distance_price: float = Field(gt=0)
    value_per_price_unit: float = Field(gt=0)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "paper"}


@app.post("/risk/check")
def risk_check(req: RiskCheckRequest) -> dict:
    state = AccountState(
        req.equity, req.start_of_day_equity, req.start_of_week_equity,
        req.peak_equity, req.open_positions, req.correlated_positions,
    )
    decision = risk_engine.check(state, req.stop_distance_price, req.value_per_price_unit)
    return {"approved": decision.approved, "reason": decision.reason, "units": decision.units}
