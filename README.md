# TJ Trading OS

TJ Trading OS is a **real-time MetaTrader 5 trading workstation** for small accounts. It combines live MT5 market data, deterministic micro-capital risk controls, parallel AI analysis, configurable research feeds, Fish Audio voice conversation, persistent trade memory, and Windows packaging.

> **Important:** Live-capable does not mean guaranteed profitable. The system can send real MT5 orders only after an explicit user confirmation for the exact proposal being executed.

## What is implemented

### Live MT5 layer

- Connect to a logged-in MetaTrader 5 terminal
- Read live account balance, equity, margin, positions and trading permission
- Read real bid/ask quotes
- Pull live MT5 candles for strategy analysis
- Read broker lot minimum, maximum and lot step
- Calculate cash loss at the proposed stop using MT5's own profit calculator
- Calculate a broker-valid lot size that stays below the configured cash-risk limit
- Run `order_check()` before `order_send()`
- Sync MT5 deal history for the journal/reflection layer

### Micro-capital risk core

Default profile:

```env
RISK_PER_TRADE=0.005
MAX_DAILY_LOSS=0.02
MAX_WEEKLY_LOSS=0.05
MAX_DRAWDOWN=0.10
MAX_OPEN_POSITIONS=1
MAX_CORRELATED_POSITIONS=1
CORRELATION_THRESHOLD=0.80
```

The OS maintains durable start-of-day, start-of-week and peak-equity anchors in SQLite. Restarting the app does not reset those anchors.

If the broker's minimum lot already exceeds the allowed cash risk at the stop, the proposal is rejected rather than rounded upward.

### Continuous live analysis

The live analysis engine can run every few seconds/minutes without creating paper fills.

Pipeline:

```text
Live MT5 quotes + candles
        ↓
Strategy registry
        ↓
Trend / momentum / ATR candidate
        ↓
Configured RSS/Atom research feeds
        ↓
Parallel AI analysts
  ├─ Technical skeptic
  ├─ Macro/news analyst
  ├─ Bull advocate
  └─ Bear advocate
        ↓
Conservative AI judge
        ↓
Portfolio-correlation gate
        ↓
Durable daily/weekly/drawdown gate
        ↓
Broker-valid micro lot sizing
        ↓
LIVE TRADE PROPOSAL
        ↓
Explicit user confirmation
        ↓
Current-price + current-risk revalidation
        ↓
MT5 order_check()
        ↓
MT5 order_send()
```

The AI cannot call `order_send()` by itself. It can only create a proposal.

### Per-proposal live confirmation

Qualified proposals receive durable IDs.

Example:

```text
Proposal #184
EURUSD BUY
Volume       0.01
Stop         1.10120
Target       1.10880
Risk cash    $0.48
AI confidence 78%
```

Before execution, TJ Trading OS re-checks:

- proposal status and age
- current market-price drift
- emergency kill switch
- MT5 trading permission
- current open-position count
- broker lot constraints
- current equity
- cash loss at the stop
- configured risk-per-trade limit

A proposal-specific live request requires a confirmation value matching that exact proposal ID.

### AI providers — Fetch Models

The UI supports:

- OpenAI
- xAI / Grok
- Anthropic
- Google Gemini
- OpenRouter
- Groq
- DeepSeek
- Mistral
- custom OpenAI-compatible endpoints

Workflow:

1. Choose provider.
2. Enter API key.
3. Select **Fetch Models**.
4. Pick a model returned by that provider.
5. Select **Use Selected Model for Engine**.

The selected credentials can be kept only in process memory. They do not need to be written into project files.

### Fish Audio voice conversation

Implemented:

- **Fetch Audio** / voice discovery
- Fish Audio ASR
- Fish Audio TTS
- microphone conversation
- floating AI chat
- animated round voice pulse

Voice states:

```text
Listening → Thinking → Speaking
```

### Journal and reflection

SQLite persists:

- risk anchors
- engine decision events
- live proposals
- submitted orders
- broker deal history
- AI post-trade reflections

The reflection agent runs on newly synced closing deals and focuses on process quality and risk discipline rather than revenge-trading or risk escalation.

### Windows executable

The repository includes:

- `run_tj.py`
- `tj_trading_os.spec`
- `scripts/build_windows.ps1`
- `.github/workflows/windows-build.yml`

The Windows workflow runs tests/lint and builds:

```text
dist\TJ-Trading-OS.exe
```

## Windows installation from source

Install:

- Windows
- Python 3.11+
- MetaTrader 5 desktop terminal

Then:

```powershell
git clone https://github.com/jazibvirk007-hue/ai-forex-trading-agent.git
cd ai-forex-trading-agent
git checkout codex/tj-trading-os-live

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[live,dev]"

Copy-Item .env.example .env
uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

If MT5 is already logged in, the integration can attach to the local terminal. Optional settings:

```env
MT5_TERMINAL_PATH=
MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=
```

Never commit a populated `.env`.

## Enable real execution

Real execution remains locked unless both values are explicitly enabled locally:

```env
ALLOW_LIVE_TRADING=true
LIVE_TRADING_ARMED=true
```

The continuous scanner still does not execute automatically. A proposal must be confirmed individually from the UI or API.

## Continuous engine configuration

```env
ENGINE_AUTO_START=false
ENGINE_CYCLE_SECONDS=30
ENGINE_SYMBOLS=EURUSD,GBPUSD,USDJPY
ENGINE_TIMEFRAME=M5
ENGINE_BARS=220
MIN_AI_CONFIDENCE=0.66
REQUIRE_AI_CONSENSUS=true
MIN_SECONDS_BETWEEN_TRADES=900
MAX_PROPOSAL_AGE_SECONDS=120
REFLECTION_ENABLED=true
```

Add comma-separated RSS or Atom feeds for the news/research agent:

```env
RESEARCH_FEED_URLS=https://example.com/feed.xml,https://example.com/markets.xml
```

## API highlights

```text
GET  /health

GET  /ai/providers
POST /ai/models/fetch
POST /ai/chat

POST /engine/ai/configure
GET  /engine/status
POST /engine/start
POST /engine/stop
POST /engine/run-once
POST /engine/emergency-stop
POST /engine/resume
GET  /engine/events
GET  /engine/proposals
POST /engine/proposals/{id}/execute

GET  /journal/trades
GET  /journal/reflections

POST /voice/fish/models/fetch
POST /voice/fish/asr
POST /voice/fish/tts

GET  /broker/mt5/status
GET  /broker/mt5/symbol/{symbol}
POST /broker/mt5/order
```

## Build the Windows EXE

```powershell
.\scripts\build_windows.ps1
```

Output:

```text
dist\TJ-Trading-OS.exe
```

## Tests

```bash
pip install -e ".[dev]"
ruff check . --fix
ruff check .
pytest -q
```

Linux CI does not install the Windows-only MetaTrader5 wheel. The MT5 adapter imports it lazily, allowing analysis, storage, strategy, provider and API components to remain testable on Linux.
