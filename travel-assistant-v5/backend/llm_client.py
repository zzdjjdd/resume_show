"""LLM 客户端：调用可配置的 OpenAI 兼容 API"""
import httpx
from typing import List, Dict, Any, Optional, AsyncIterator


class LLMClient:
    """统一的 LLM 客户端，支持任意 OpenAI 兼容服务"""

    def __init__(self, api_key: str, base_url: str, model: str, timeout: int = 60):
        self.api_key = api_key
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        self.timeout = timeout

    def _endpoint(self) -> str:
        # 自动补齐路径
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/chat/completions"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def list_models(self) -> List[Dict[str, Any]]:
        """获取可用模型列表"""
        if not self.api_key or not self.base_url:
            return []
        url = self.base_url
        if url.endswith("/chat/completions"):
            url = url.rsplit("/", 1)[0]
        if not url.endswith("/v1"):
            url = url + "/v1"
        url = url + "/models"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(url, headers=self._headers())
                r.raise_for_status()
                data = r.json()
                return data.get("data", []) if isinstance(data, dict) else []
        except Exception:
            return []

    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
        temperature: float = 0.7,
        reasoning_split: bool = True,
    ) -> Any:
        """对话请求（非流式）。如果 tools 提供则带上。"""
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        # 通用请求：让支持 OpenAI reasoning 接口的厂商把思考内容分离到 reasoning_details
        if reasoning_split:
            payload["reasoning_split"] = True
            payload["extra_body"] = {"reasoning_split": True}
        url = self._endpoint()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(url, json=payload, headers=self._headers())
            r.raise_for_status()
            return r.json()

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """流式对话请求"""
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        url = self._endpoint()
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, json=payload, headers=self._headers()) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        chunk = line[5:].strip()
                        if chunk and chunk != "[DONE]":
                            try:
                                import json
                                obj = json.loads(chunk)
                                content = (
                                    obj.get("choices", [{}])[0]
                                    .get("delta", {})
                                    .get("content")
                                )
                                if content:
                                    yield content
                            except Exception:
                                continue

    async def test_connection(self) -> Dict[str, Any]:
        """测试 API 连接 + 鉴权"""
        if not self.api_key:
            return {"ok": False, "error": "API Key 为空"}
        if not self.base_url:
            return {"ok": False, "error": "Base URL 为空"}
        try:
            url = self.base_url
            if url.endswith("/chat/completions"):
                url = url.rsplit("/", 1)[0]
            if not url.endswith("/v1"):
                url = url + "/v1"
            models_url = url + "/models"
            async with httpx.AsyncClient(timeout=min(self.timeout, 15)) as client:
                r = await client.get(models_url, headers=self._headers())
                r.raise_for_status()
                data = r.json()
                count = len(data.get("data", [])) if isinstance(data, dict) else 0
                return {"ok": True, "models_count": count, "model_used": self.model}
        except httpx.HTTPStatusError as e:
            return {"ok": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
