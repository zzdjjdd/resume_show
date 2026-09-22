"""OpenAI 兼容 LLM 客户端。

参考原 apps/api/src/interview-agent/llm/llm-client.service.ts 与
resumes.controller.ts 中的 fetch 逻辑。支持 thinking 控制、JSON 提取、超时。
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx

from .. import config

DEFAULT_TIMEOUT_MS = 120000


class LlmContentError(Exception):
    """模型返回的内容无法解析为期望结构。"""


def normalize_base_url(base_url: str) -> str:
    return base_url.strip().rstrip("/")


def parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    v = str(value or "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return None


class LlmClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        enable_thinking: bool | None = None,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ):
        self.base_url = normalize_base_url(base_url or config.resolve_interview_base_url())
        self.api_key = (api_key or config.resolve_interview_api_key()).strip()
        self.model = model or config.resolve_interview_model()
        if enable_thinking is None:
            enable_thinking = config.resolve_interview_enable_thinking()
        self.enable_thinking = enable_thinking
        self.timeout_ms = timeout_ms

    def has_provider(self) -> bool:
        return bool(self.api_key)

    # ---- 文本/JSON 提取 ----
    @staticmethod
    def _extract_balanced_json(raw: str) -> dict | None:
        """从任意文本中提取第一个括号平衡的 JSON 对象（容忍前后多余文字）。"""
        start = raw.find("{")
        while start != -1:
            depth = 0
            in_str = False
            esc = False
            for i in range(start, len(raw)):
                ch = raw[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(raw[start : i + 1])
                        except json.JSONDecodeError:
                            break
            start = raw.find("{", start + 1)
        return None

    @staticmethod
    def try_parse_json(raw: str) -> dict | None:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
        # 兼容包裹在 ```json ... ``` 中的输出
        matched = re.search(r"```json\s*([\s\S]*?)```", raw, re.IGNORECASE)
        if matched:
            try:
                return json.loads(matched.group(1))
            except (json.JSONDecodeError, TypeError):
                pass
        # 兼容任意代码块包裹
        matched = re.search(r"```\s*([\s\S]*?)```", raw)
        if matched:
            parsed = LlmClient._extract_balanced_json(matched.group(1))
            if parsed is not None:
                return parsed
        # 最后兑底：从全文提取括号平衡的 JSON 对象
        return LlmClient._extract_balanced_json(raw)

    @staticmethod
    def extract_text_content(data: dict) -> str:
        direct = data.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()

        choices = data.get("choices") if isinstance(data.get("choices"), list) else []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message") if isinstance(choice.get("message"), dict) else None
            delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else None

            msg_content = message.get("content") if message else None
            if isinstance(msg_content, str) and msg_content.strip():
                return msg_content.strip()
            if isinstance(msg_content, list):
                joined = "".join(
                    str(item.get("text", ""))
                    for item in msg_content
                    if isinstance(item, dict)
                ).strip()
                if joined:
                    return joined
            if message and isinstance(message.get("reasoning_content"), str) and message["reasoning_content"].strip():
                return message["reasoning_content"].strip()
            if delta and isinstance(delta.get("content"), str) and delta["content"].strip():
                return delta["content"].strip()
            if delta and isinstance(delta.get("reasoning_content"), str) and delta["reasoning_content"].strip():
                return delta["reasoning_content"].strip()

            candidate = LlmClient._collect_by_preferred_keys(choice, 5)
            if candidate:
                return candidate

        fallback = LlmClient._collect_by_preferred_keys(data, 6)
        if fallback:
            return fallback
        return ""

    @staticmethod
    def _collect_by_preferred_keys(node: Any, max_depth: int) -> str:
        preferred = {"content", "text", "output_text", "reasoning_content", "answer", "final_answer"}
        out: list[str] = []

        def walk(value: Any, depth: int):
            if depth > max_depth or value is None:
                return
            if isinstance(value, str):
                trimmed = value.strip()
                if trimmed:
                    out.append(trimmed)
                return
            if isinstance(value, list):
                for item in value:
                    walk(item, depth + 1)
                return
            if isinstance(value, dict):
                for key, sub in value.items():
                    if key in preferred:
                        walk(sub, depth + 1)

        walk(node, 0)
        return "\n".join(out).strip()

    # ---- 请求 ----
    def _build_payload(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        response_format: dict | None = None,
        stream: bool = False,
        disable_thinking: bool = False,
    ) -> dict:
        payload: dict = {
            "model": self.model,
            "stream": stream,
            "temperature": temperature,
            "enable_thinking": False,
            "messages": messages,
        }
        if self.enable_thinking is not None and not disable_thinking:
            payload["enable_thinking"] = self.enable_thinking
        if disable_thinking:
            payload["enable_thinking"] = False
            payload["extra_body"] = {"enable_thinking": False}
        if response_format:
            payload["response_format"] = response_format
        return payload

    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        response_format: dict | None = None,
        timeout_ms: int | None = None,
    ) -> str:
        """发起一次 chat 请求，返回提取出的文本内容。失败抛 LlmContentError。

        兼容 thinking 输出为空的情况：先正常请求，若 choices 为空则用关闭 thinking 重试一次。
        """
        timeout_ms = timeout_ms or self.timeout_ms
        payload = self._build_payload(messages, temperature, response_format)
        data = await self._post(payload, timeout_ms)
        content = self.extract_text_content(data)
        if not content and isinstance(data.get("choices"), list) and len(data["choices"]) == 0:
            # 重试：关闭 thinking
            retry_payload = self._build_payload(
                messages, temperature, response_format, disable_thinking=True
            )
            data = await self._post(retry_payload, timeout_ms)
            content = self.extract_text_content(data)
        if not content:
            summary = {
                "keys": list(data.keys())[:12],
                "choicesLength": len(data.get("choices") or []),
            }
            raise LlmContentError(f"模型返回为空（响应摘要：{json.dumps(summary, ensure_ascii=False)}）")
        return content

    async def chat_json(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        timeout_ms: int | None = None,
    ) -> dict:
        """请求并解析为 JSON 对象，失败抛 LlmContentError。

        兼容策略：先带 response_format=json_object 请求；若服务商不支持或
        输出无法解析，自动降级为普通请求并用强化提取器再试一次。
        """
        try:
            content = await self.chat(
                messages,
                temperature=temperature,
                response_format={"type": "json_object"},
                timeout_ms=timeout_ms,
            )
            parsed = self.try_parse_json(content)
            if parsed is not None:
                return parsed
        except LlmContentError:
            # 部分服务商会拒绝 response_format 参数，降级重试
            pass
        content = await self.chat(messages, temperature=temperature, timeout_ms=timeout_ms)
        parsed = self.try_parse_json(content)
        if parsed is None:
            raise LlmContentError("模型未返回合法 JSON（已重试一次），请再次尝试或更换模型")
        return parsed

    async def _post(self, payload: dict, timeout_ms: int) -> dict:
        if not self.api_key:
            raise LlmContentError(
                "缺少模型配置：请配置 INTERVIEW_API_KEY / INTERVIEW_BASE_URL / INTERVIEW_MODEL"
            )
        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        async with httpx.AsyncClient(timeout=timeout_ms / 1000) as client:
            resp = await client.post(endpoint, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise LlmContentError(
                f"上游模型调用失败（{resp.status_code}）：{resp.text[:500]}"
            )
        try:
            return resp.json()
        except json.JSONDecodeError:
            raise LlmContentError("上游返回非 JSON 响应")
