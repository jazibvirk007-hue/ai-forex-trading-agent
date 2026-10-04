from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .risk import AccountState


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sqlite_path(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("TJ Trading OS currently requires a sqlite:/// database URL")
    return Path(database_url[len(prefix):]).expanduser().resolve()


class TradingStore:
    """Durable state for risk anchors, proposals, trades, broker deals and reflections."""

    def __init__(self, database_url: str) -> None:
        self.path = _sqlite_path(database_url)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS risk_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    day_key TEXT NOT NULL,
                    week_key TEXT NOT NULL,
                    start_day_equity REAL NOT NULL,
                    start_week_equity REAL NOT NULL,
                    peak_equity REAL NOT NULL,
                    kill_switch INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS engine_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    level TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    symbol TEXT,
                    message TEXT NOT NULL,
                    payload TEXT
                );

                CREATE TABLE IF NOT EXISTS trade_proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    volume_lots REAL NOT NULL,
                    reference_entry REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    estimated_risk_cash REAL NOT NULL,
                    strategy TEXT NOT NULL,
                    technical_confidence REAL NOT NULL,
                    ai_confidence REAL NOT NULL,
                    rationale TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ready'
                );

                CREATE TABLE IF NOT EXISTS trade_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_id TEXT,
                    volume_lots REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    risk_cash REAL NOT NULL,
                    strategy TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    rationale TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'submitted'
                );

                CREATE TABLE IF NOT EXISTS broker_deals (
                    ticket TEXT PRIMARY KEY,
                    position_id TEXT,
                    symbol TEXT NOT NULL,
                    side TEXT,
                    entry_type TEXT,
                    volume REAL,
                    price REAL,
                    profit REAL,
                    commission REAL,
                    swap REAL,
                    occurred_at TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reflections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    deal_ticket TEXT NOT NULL UNIQUE,
                    symbol TEXT NOT NULL,
                    pnl REAL NOT NULL,
                    reflection TEXT NOT NULL
                );
                """
            )

    def account_state(
        self,
        equity: float,
        open_positions: int,
        correlated_positions: int = 0,
        now: datetime | None = None,
    ) -> AccountState:
        now = now or _utc_now()
        day_key = now.date().isoformat()
        iso = now.isocalendar()
        week_key = f"{iso.year}-W{iso.week:02d}"
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM risk_state WHERE id = 1").fetchone()
            if row is None:
                start_day = start_week = peak = equity
                conn.execute(
                    """
                    INSERT INTO risk_state
                    (id, day_key, week_key, start_day_equity, start_week_equity,
                     peak_equity, kill_switch, updated_at)
                    VALUES (1, ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (day_key, week_key, equity, equity, equity, now.isoformat()),
                )
            else:
                start_day = float(row["start_day_equity"])
                start_week = float(row["start_week_equity"])
                peak = max(float(row["peak_equity"]), equity)
                if row["day_key"] != day_key:
                    start_day = equity
                if row["week_key"] != week_key:
                    start_week = equity
                conn.execute(
                    """
                    UPDATE risk_state
                    SET day_key=?, week_key=?, start_day_equity=?,
                        start_week_equity=?, peak_equity=?, updated_at=?
                    WHERE id=1
                    """,
                    (day_key, week_key, start_day, start_week, peak, now.isoformat()),
                )
        return AccountState(
            equity=equity,
            start_of_day_equity=start_day,
            start_of_week_equity=start_week,
            peak_equity=peak,
            open_positions=open_positions,
            correlated_positions=correlated_positions,
        )

    def kill_switch(self) -> bool:
        with self.connection() as conn:
            row = conn.execute("SELECT kill_switch FROM risk_state WHERE id=1").fetchone()
            return bool(row["kill_switch"]) if row else False

    def set_kill_switch(self, enabled: bool, equity: float = 0.0) -> None:
        now = _utc_now()
        with self.connection() as conn:
            row = conn.execute("SELECT id FROM risk_state WHERE id=1").fetchone()
            if row is None:
                safe_equity = max(float(equity), 0.01)
                iso = now.isocalendar()
                conn.execute(
                    """
                    INSERT INTO risk_state
                    (id, day_key, week_key, start_day_equity, start_week_equity,
                     peak_equity, kill_switch, updated_at)
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now.date().isoformat(),
                        f"{iso.year}-W{iso.week:02d}",
                        safe_equity,
                        safe_equity,
                        safe_equity,
                        int(enabled),
                        now.isoformat(),
                    ),
                )
            else:
                conn.execute(
                    "UPDATE risk_state SET kill_switch=?, updated_at=? WHERE id=1",
                    (int(enabled), now.isoformat()),
                )

    def event(
        self,
        event_type: str,
        message: str,
        *,
        level: str = "info",
        symbol: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO engine_events
                (created_at, level, event_type, symbol, message, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_now().isoformat(),
                    level,
                    event_type,
                    symbol,
                    message,
                    json.dumps(payload, default=str) if payload is not None else None,
                ),
            )

    def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM engine_events ORDER BY id DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_proposal(
        self,
        *,
        symbol: str,
        side: str,
        volume_lots: float,
        reference_entry: float,
        stop_loss: float,
        take_profit: float,
        estimated_risk_cash: float,
        strategy: str,
        technical_confidence: float,
        ai_confidence: float,
        rationale: str,
    ) -> int:
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO trade_proposals
                (created_at, symbol, side, volume_lots, reference_entry,
                 stop_loss, take_profit, estimated_risk_cash, strategy,
                 technical_confidence, ai_confidence, rationale, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready')
                """,
                (
                    _utc_now().isoformat(),
                    symbol,
                    side,
                    volume_lots,
                    reference_entry,
                    stop_loss,
                    take_profit,
                    estimated_risk_cash,
                    strategy,
                    technical_confidence,
                    ai_confidence,
                    rationale,
                ),
            )
            return int(cursor.lastrowid)

    def proposal(self, proposal_id: int) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM trade_proposals WHERE id=?",
                (proposal_id,),
            ).fetchone()
        return dict(row) if row else None

    def recent_proposals(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM trade_proposals ORDER BY id DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_proposal_status(self, proposal_id: int, status: str) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE trade_proposals SET status=? WHERE id=?",
                (status, proposal_id),
            )

    def record_trade(
        self,
        *,
        symbol: str,
        side: str,
        order_id: str | None,
        volume_lots: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        risk_cash: float,
        strategy: str,
        confidence: float,
        rationale: str,
        status: str = "submitted",
    ) -> int:
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO trade_journal
                (created_at, symbol, side, order_id, volume_lots, entry_price,
                 stop_loss, take_profit, risk_cash, strategy, confidence,
                 rationale, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_now().isoformat(),
                    symbol,
                    side,
                    order_id,
                    volume_lots,
                    entry_price,
                    stop_loss,
                    take_profit,
                    risk_cash,
                    strategy,
                    confidence,
                    rationale,
                    status,
                ),
            )
            return int(cursor.lastrowid)

    def recent_trades(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM trade_journal ORDER BY id DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def last_trade_time(self, symbol: str) -> datetime | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT created_at FROM trade_journal
                WHERE symbol=? AND status='submitted'
                ORDER BY id DESC LIMIT 1
                """,
                (symbol,),
            ).fetchone()
        return datetime.fromisoformat(str(row["created_at"])) if row else None

    def upsert_deal(self, deal: dict[str, Any]) -> bool:
        ticket = str(deal["ticket"])
        with self.connection() as conn:
            exists = conn.execute(
                "SELECT 1 FROM broker_deals WHERE ticket=?",
                (ticket,),
            ).fetchone()
            if exists:
                return False
            conn.execute(
                """
                INSERT INTO broker_deals
                (ticket, position_id, symbol, side, entry_type, volume, price,
                 profit, commission, swap, occurred_at, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticket,
                    str(deal.get("position_id") or ""),
                    str(deal.get("symbol") or ""),
                    deal.get("side"),
                    deal.get("entry_type"),
                    float(deal.get("volume") or 0),
                    float(deal.get("price") or 0),
                    float(deal.get("profit") or 0),
                    float(deal.get("commission") or 0),
                    float(deal.get("swap") or 0),
                    str(deal.get("occurred_at") or _utc_now().isoformat()),
                    json.dumps(deal, default=str),
                ),
            )
            return True

    def record_reflection(
        self,
        deal_ticket: str,
        symbol: str,
        pnl: float,
        reflection: str,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO reflections
                (created_at, deal_ticket, symbol, pnl, reflection)
                VALUES (?, ?, ?, ?, ?)
                """,
                (_utc_now().isoformat(), deal_ticket, symbol, pnl, reflection),
            )

    def recent_reflections(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM reflections ORDER BY id DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def risk_snapshot(self) -> dict[str, Any]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM risk_state WHERE id=1").fetchone()
        return dict(row) if row else {}

    @staticmethod
    def account_state_payload(state: AccountState) -> dict[str, Any]:
        return asdict(state)
