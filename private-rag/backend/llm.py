"""MiniMax-M3 调用(OpenAI 兼容 + reasoning_split)。"""
from __future__ import annotations

from typing import List, Optional

from openai import OpenAI

from .config import settings


class LLMError(RuntimeError):
    pass


def _client() -> OpenAI:
    if not settings.MINIMAX_API_KEY:
        raise LLMError("MINIMAX_API_KEY 未配置(.env)")
    return OpenAI(
        api_key=settings.MINIMAX_API_KEY,
        base_url=settings.MINIMAX_BASE_URL,
    )


def chat(
    messages: List[dict],
    model: Optional[str] = None,
    temperature: float = 0.3,
    reasoning_split: bool = True,
) -> dict:
    """返回 {"content": str, "reasoning": Optional[str]}。"""
    client = _client()
    model = model or settings.LLM_MODEL
    extra_body = {"reasoning_split": True} if reasoning_split else None

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            extra_body=extra_body,
        )
    except Exception as e:
        raise LLMError(f"MiniMax-M3 调用失败: {e}") from e

    msg = resp.choices[0].message
    content = msg.content or ""

    # reasoning_split=True 时,思考内容会放在 reasoning_details 里
    reasoning: Optional[str] = None
    details = getattr(msg, "reasoning_details", None)
    if details:
        try:
            pieces = []
            for d in details:
                if isinstance(d, dict):
                    t = d.get("text") or d.get("reasoning") or ""
                else:
                    t = getattr(d, "text", "") or ""
                if t:
                    pieces.append(t)
            if pieces:
                reasoning = "\n".join(pieces)
        except Exception:
            reasoning = None

    return {"content": content, "reasoning": reasoning}