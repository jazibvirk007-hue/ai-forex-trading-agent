# TJ Trading OS

A live-first AI trading workstation built around **real MetaTrader 5 execution**, micro-capital risk gates, dynamic AI providers, Fish Audio voice conversation, and a floating trading copilot.

> **Important:** Live-capable does not mean guaranteed profitable. The software can route real orders when explicitly armed, but no model, strategy, or AI provider can guarantee returns.

## Current live foundation

- MetaTrader 5 live account connection
- Real bid/ask quote retrieval
- Broker minimum/maximum/step volume validation
- Pre-flight `order_check()` before `order_send()`
- Hard stop-loss and take-profit requirement
- Stop-loss cash-risk calculation against current account equity
- Micro-capital default: **0.5% risk per trade**
- Micro-capital default: **1 open position**
- Two environment arm flags plus `X-Live-Confirm: LIVE` required for execution
- Dynamic AI provider list with **Fetch Models**
- OpenAI, xAI/Grok, OpenRouter, Groq, DeepSeek, Mistral, Anthropic, Gemini, and custom OpenAI-compatible endpoints
- Fish Audio **Fetch Audio** voice-model loading
- Fish Audio TTS and ASR
- Floating AI chat window
- Microphone voice conversation
- Round pulse orb for listening, thinking, and speaking states

## Architecture

```text
Live MT5 data ───────────────┐
                             │
AI provider + research ──────┼──> TJ Copilot / strategy layer
                             │
Fish ASR <── microphone      │
Fish TTS ──> spoken reply    │
                             ▼
                    deterministic risk gate
                             │
                 broker volume validation
                             │
                    MT5 order_check()
                             │
                      explicit live arm
                             │
                      MT5 order_send()
```

The AI layer is intentionally separated from the final execution gate. A model cannot bypass the configured broker/risk checks.

## Windows live installation

MetaTrader 5's official Python package is Windows-only. Install Python 3.11+ and MetaTrader 5 first.

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

Open `http://127.0.0.1:8000`.

## MT5 connection

If the local MetaTrader 5 terminal is already signed in, the Python integration can normally attach to it without storing the account password in this project.

Optional environment values:

```env
MT5_TERMINAL_PATH=
MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=
```

Do not commit a populated `.env` file.

## Enabling real order execution

The application starts live-ready but **execution locked**. After verifying the connected MT5 account and risk configuration, the local environment must explicitly contain:

```env
BROKER_MODE=live
BROKER_NAME=mt5
ALLOW_LIVE_TRADING=true
LIVE_TRADING_ARMED=true
```

The order endpoint additionally requires:

```http
X-Live-Confirm: LIVE
```

This prevents an AI/chat request or accidental HTTP call from silently arming the account.

## Micro-capital profile

Default limits:

```env
RISK_PER_TRADE=0.005
MAX_DAILY_LOSS=0.02
MAX_WEEKLY_LOSS=0.05
MAX_DRAWDOWN=0.10
MAX_OPEN_POSITIONS=1
MAX_CORRELATED_POSITIONS=1
```

Before a live order is accepted, TJ Trading OS calculates the approximate loss at the supplied stop using MT5's own profit calculator. If that loss exceeds the configured percentage of current equity, the order is rejected.

If the broker's minimum lot size is already too large for the account's risk allowance, the system rejects the order instead of rounding the volume upward.

## AI Providers — Fetch Models

In the dashboard:

1. Choose the provider.
2. Enter its API key.
3. For a custom OpenAI-compatible endpoint, enter the base URL.
4. Select **Fetch Models**.
5. Choose a returned model.

API keys entered in the dashboard are sent to the local backend for the requested call and are not written to project files by the UI.

## Fish Audio — Fetch Audio

1. Enter the Fish Audio API key.
2. Select **Fetch Audio** to retrieve available voice models.
3. Choose a voice and speech model.
4. Open the floating chat.
5. Tap the round voice button to start speaking and tap again to stop.

The pulse orb appears while listening, changes state while the AI is thinking, and remains visible while Fish Audio speaks the response.

Fish Audio integration uses the production `/model`, `/v1/tts`, and `/v1/asr` APIs.

## API highlights

```text
GET  /health
GET  /ai/providers
POST /ai/models/fetch
POST /ai/chat

POST /voice/fish/models/fetch
POST /voice/fish/asr
POST /voice/fish/tts

GET  /broker/mt5/status
GET  /broker/mt5/symbol/{symbol}
POST /broker/mt5/order
```

## Tests

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

The Linux CI deliberately does not install the Windows-only MT5 wheel; the MT5 adapter imports it lazily so the rest of the system remains testable on CI.
