from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

from ..domain import Side
from ..integrations.ai import AIProviderClient
from ..research import ResearchSnapshot
from ..strategies.registry import StrategyCandidate


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class AgentConsensus:
    action: str
    confidence: float
    rationale: str
    agent_views: dict[str, str]

    @property
    def side(self) -> Side | None:
        if self.action == "buy":
            return Side.BUY
        if self.action == "sell":
            return Side.SELL
        return None


class MultiAgentOrchestrator:
    """Parallel analyst debate. The model recommends; deterministic code executes."""

    def __init__(
        self,
        client: AIProviderClient,
        provider: str,
        model: str,
        api_key: str,
        base_url: str | None = None,
    ) -> None:
        self.client = client
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    async def _call(self, system: str, user: str) -> str:
        return await self.client.chat(
            provider=self.provider,
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

    @staticmethod
    def _market_text(candidate: StrategyCandidate, research: ResearchSnapshot) -> str:
        diagnostics = json.dumps(candidate.diagnostics, sort_keys=True)
        return (
            f"Symbol: {candidate.symbol}\n"
            f"Technical candidate: {candidate.side.value}\n"
            f"Technical confidence: {candidate.confidence:.3f}\n"
            f"Entry reference: {candidate.entry_reference}\n"
            f"Stop distance: {candidate.stop_distance}\n"
            f"Target distance: {candidate.target_distance}\n"
            f"Diagnostics: {diagnostics}\n\n"
            f"Recent research/headlines:\n{research.prompt_text()}"
        )

    async def analyze(
        self, candidate: StrategyCandidate, research: ResearchSnapshot
    ) -> AgentConsensus:
        context = self._market_text(candidate, research)
        roles = {
            "technical": (
                "You are a skeptical technical-market analyst. Evaluate only the supplied "
                "market diagnostics. Call out weak trend, overextension, bad spread, or missing "
                "confirmation. Do not invent prices or data."
            ),
            "macro": (
                "You are a macro/news risk analyst. Evaluate the supplied headlines and whether "
                "they support, oppose, or add event risk to the technical candidate. If news is "
                "missing, explicitly say uncertainty is high. Do not invent events."
            ),
            "bull": (
                "You are the bullish advocate in an investment debate. Build the strongest "
                "evidence-based case for a long position from supplied facts, while stating the "
                "main invalidation. Never fabricate data."
            ),
            "bear": (
                "You are the bearish advocate in an investment debate. Build the strongest "
                "evidence-based case for a short position from supplied facts, while stating the "
                "main invalidation. Never fabricate data."
            ),
        }
        responses = await asyncio.gather(
            *(self._call(system, context) for system in roles.values())
        )
        views = dict(zip(roles, responses, strict=True))

        judge_prompt = (
            f"{context}\n\n"
            "Independent analyst views:\n"
            + "\n".join(f"[{name}] {text}" for name, text in views.items())
            + "\n\nReturn one strict JSON object only with keys: "
            'action ("buy", "sell", or "skip"), confidence (0.0 to 1.0), '
            "rationale (one concise sentence). Prefer skip when evidence conflicts, "
            "when external information is insufficient, or when confidence is weak. "
            "Do not choose position size; risk code handles that."
        )
        judged = await self._call(
            "You are the final trading debate judge. Be conservative and evidence-bound. "
            "You cannot execute trades and you must never override risk controls.",
            judge_prompt,
        )
        match = _JSON_RE.search(judged)
        if not match:
            return AgentConsensus("skip", 0.0, "Judge returned invalid structured output.", views)
        try:
            payload: dict[str, Any] = json.loads(match.group(0))
            action = str(payload.get("action", "skip")).lower()
            if action not in {"buy", "sell", "skip"}:
                action = "skip"
            confidence = float(payload.get("confidence", 0.0))
            confidence = min(1.0, max(0.0, confidence))
            rationale = str(payload.get("rationale", "")).strip()[:800]
            return AgentConsensus(action, confidence, rationale or "No rationale.", views)
        except (ValueError, TypeError, json.JSONDecodeError):
            return AgentConsensus("skip", 0.0, "Judge output could not be parsed.", views)

    async def reflect(self, deal: dict[str, Any]) -> str:
        prompt = (
            "Review this completed broker deal and extract one or two reusable process lessons. "
            "Do not claim causality that cannot be supported and do not propose increasing risk "
            f"to recover losses. Deal: {json.dumps(deal, default=str)}"
        )
        return await self._call(
            "You are the TJ Trading OS post-trade reflection agent. Focus on process quality, "
            "risk discipline, and uncertainty. Keep the response under 180 words.",
            prompt,
        )
