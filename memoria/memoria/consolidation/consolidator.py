"""Consolidation: turn raw experience into durable knowledge.

Two jobs, each with an optional LLM upgrade path and a deterministic fallback:
- ``distill_facts``: extract stable facts from episodic memory into semantic
  memory. With an LLM configured, facts are model-extracted (JSON); otherwise a
  regex heuristic is used. Idempotent via semantic upsert dedup + lineage.
- ``summarize_working``: compress working memory into one episodic event —
  LLM-summarized when available, else extractive concatenation.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from ..errors import MemoriaError
from ..llms.base import LLM
from ..stores.episodic import EpisodicStore
from ..stores.semantic import SemanticStore
from ..stores.working import WorkingMemory

# Heuristic fallback: "this episode contains a stable fact worth keeping".
FACT_PATTERN = re.compile(
    r"喜欢|偏好|爱|习惯|总是|讨厌|想要|不喜欢|prefer|like|always|usually|hate"
)

DISTILL_SYSTEM = "你是记忆系统的事实抽取器，从对话事件中抽取用户稳定的事实、偏好或习惯。"
DISTILL_PROMPT = """下面是若干条记忆事件，格式为 (id=事件id) 内容。
请抽取其中关于用户的稳定事实或偏好，仅以 JSON 数组返回。
每项形如 {{"episode_id": "事件id", "fact": "事实"}}。
若无值得抽取的事实，返回 []。不要输出解释或代码块标记。

事件：
{episodes}
"""

SUMMARY_SYSTEM = "你是记忆系统的摘要器。"
SUMMARY_PROMPT = "请用一句简洁的中文总结以下对话的核心信息，只输出摘要本身：\n{conversation}"


def _parse_facts(raw: str) -> list[dict[str, Any]]:
    """Best-effort parse of the LLM's JSON fact list (tolerant of fences)."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1]
        if "```" in text:
            text = text.rsplit("```", 1)[0]
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict) and str(item.get("fact", "")).strip()]


class Consolidator:
    def __init__(
        self,
        episodic: EpisodicStore,
        semantic: SemanticStore,
        working: WorkingMemory,
        subject: str = "用户",
        fact_pattern: re.Pattern[str] = FACT_PATTERN,
        fact_confidence: float = 0.8,
        llm: LLM | None = None,
    ) -> None:
        self._episodic = episodic
        self._semantic = semantic
        self._working = working
        self._subject = subject
        self._pattern = fact_pattern
        self._fact_confidence = fact_confidence
        self._llm = llm
        self._distilled_ids: set[str] = set()  # incremental: only process new episodes

    def distill_facts(self, extractor: Callable[[str], bool] | None = None) -> int:
        """Upsert stable facts found in episodic memory. Returns facts written.

        Priority: explicit ``extractor`` > LLM (if configured) > regex heuristic.
        """
        if extractor is not None:
            return self._distill_by_predicate(extractor)
        if self._llm is not None:
            try:
                return self._distill_with_llm()
            except MemoriaError:
                pass  # provider failure -> fall back to heuristic
        return self._distill_by_predicate(lambda text: bool(self._pattern.search(text)))

    def _distill_by_predicate(self, is_fact: Callable[[str], bool]) -> int:
        rows = self._episodic.list_all()
        new_rows = [row for row in rows if row.id not in self._distilled_ids]
        distilled = 0
        for row in new_rows:
            if is_fact(row.content):
                self._semantic.upsert(
                    subject=self._subject,
                    fact=row.content,
                    confidence=self._fact_confidence,
                    source_episode_ids=[row.id],
                )
                distilled += 1
        self._distilled_ids.update(row.id for row in rows)
        return distilled

    def _distill_with_llm(self) -> int:
        assert self._llm is not None
        rows = self._episodic.list_all()
        new_rows = [row for row in rows if row.id not in self._distilled_ids]
        if not new_rows:
            return 0
        episodes = "\n".join(f"(id={row.id}) {row.content}" for row in new_rows)
        raw = self._llm.complete(
            DISTILL_PROMPT.format(episodes=episodes), system=DISTILL_SYSTEM
        )
        valid_ids = {row.id for row in new_rows}
        distilled = 0
        for item in _parse_facts(raw):
            fact = str(item["fact"]).strip()
            episode_id = str(item.get("episode_id", "")).strip()
            sources = [episode_id] if episode_id in valid_ids else None
            self._semantic.upsert(
                subject=self._subject,
                fact=fact,
                confidence=self._fact_confidence,
                source_episode_ids=sources,
            )
            distilled += 1
        self._distilled_ids.update(row.id for row in rows)
        return distilled

    def summarize_working(self, clear: bool = True) -> str | None:
        """Compress working memory into one episodic summary. Returns its id."""
        if len(self._working) == 0:
            return None
        conversation = "\n".join(f"{m.role}: {m.content}" for m in self._working.messages)
        summary: str | None = None
        if self._llm is not None:
            try:
                candidate = self._llm.complete(
                    SUMMARY_PROMPT.format(conversation=conversation), system=SUMMARY_SYSTEM
                ).strip()
                summary = candidate or None
            except MemoriaError:
                summary = None
        if not summary:
            summary = " | ".join(f"{m.role}:{m.content}" for m in self._working.messages)
        record_id = self._episodic.add("对话摘要: " + summary, importance=0.6)
        if clear:
            self._working.clear()
        return record_id
