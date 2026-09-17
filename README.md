# AI Forex Trading Agent

Risk-first research and execution framework for forex. Designed for backtesting, walk-forward validation, paper trading, and controlled live execution.

> **Safety:** This software does not guarantee profits. Live trading is disabled by default. Use a demo account until the complete research, validation, risk, and operational process has been independently verified.

## Architecture

```text
Market Data
    │
    ├── Historical / Live adapters
    ▼
Data Normalization → Feature Engine → Multi-Timeframe Dataset
                                      │
                                      ▼
                         Strategy / ML Ensemble
                                      │
                                      ▼
                           Edge & Cost Filter
                                      │
                                      ▼
                                Risk Engine
                                      │
                                      ▼
                           Execution Abstraction
                            │                  │
                       Paper Broker       Live Broker
                            │                  │
                            └──────┬───────────┘
                                   ▼
                         Orders / Positions / DB
                                   │
                                   ▼
                         Monitoring + Audit Logs
```

## Initial safety limits

- Risk per trade: 0.5% equity maximum
- Daily loss: 2% maximum
- Weekly loss: 5% maximum
- Maximum drawdown: 10% → trading halted
- Maximum open positions: 3
- Maximum correlated positions: 2
- Every accepted trade requires a hard stop loss
- No martingale, grid recovery, or averaging down
- Dry-run/paper mode is the default

## Repository layout

```text
app/
  api.py                 FastAPI service
  config.py              Typed environment/config settings
  domain.py              Core trading data models
  risk.py                Risk and position sizing engine
  strategy.py            Baseline deterministic signal layer
  backtest.py            Cost-aware event backtest primitives
  brokers/base.py        Broker abstraction
  brokers/paper.py       Paper broker
  features/indicators.py Technical indicators
  data/csv_provider.py   CSV historical-data adapter
  main.py                Application entry point
config/
  default.yaml           Safe default configuration
tests/
  test_risk.py           Risk-engine tests
  test_strategy.py       Strategy tests
Dockerfile
docker-compose.yml
.env.example
pyproject.toml
```

## Quick start

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
pytest
uvicorn app.api:app --reload
```

The API exposes `/health` and `/risk/check`. No broker credentials are required for the initial scaffold.

## Development stages

1. Historical data ingestion and quality checks
2. Feature engineering and leakage-safe datasets
3. Baseline strategy and cost model
4. Event-driven backtest
5. Walk-forward and out-of-sample validation
6. Monte Carlo / stress testing
7. Paper broker
8. Broker adapters and live execution behind explicit safety gates
9. Monitoring, alerts, reconciliation and operational controls
10. ML ensemble experiments with reproducible model registry
