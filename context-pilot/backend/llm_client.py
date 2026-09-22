"""
LLM client - calls configured LLM API (default: MiniMax via OpenAI-compatible API)
"""
import os
import json
from typing import List, Dict, Any, Optional
import httpx


class LLMClient:
    """LLM API client supporting OpenAI-compatible APIs"""

    def __init__(self):
        self.base_url: str = "https://api.minimaxi.com/v1"
        self.api_key: str = ""
        self.model: str = "MiniMax-M3"
        self.temperature: float = 0.7
        self.max_tokens: int = 2048
        self.use_reasoning: bool = True

    def configure(self, base_url: str, api_key: str, model: str, temperature: float = 0.7):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.temperature = temperature

    def test_connection(self) -> Dict[str, Any]:
        """Test LLM connection"""
        if not self.api_key:
            return {"success": False, "message": "API Key未配置"}
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 10
                },
                timeout=30.0
            )
            if response.status_code == 200:
                return {"success": True, "message": f"LLM连接成功 ({self.model})"}
            return {"success": False, "message": f"HTTP {response.status_code}: {response.text[:200]}"}
        except Exception as e:
            return {"success": False, "message": f"连接错误: {str(e)}"}

    def chat(self, messages: List[Dict[str, str]]) -> str:
        """Send a chat request to the LLM"""
        if not self.api_key:
            return self._mock_response(messages)
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens
            }
            if self.use_reasoning and "minimaxi" in self.base_url.lower():
                payload["extra_body"] = {"reasoning_split": True}

            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=60.0
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return content
        except Exception as e:
            print(f"LLM call error: {e}")
            return self._mock_response(messages)

    def _mock_response(self, messages: List[Dict[str, str]]) -> str:
        """Mock response when API is not configured - for demo purposes"""
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break
        # Simple mock based on user input
        if "你好" in last_user or "hello" in last_user.lower():
            return "你好！我是 Context Pilot 助手，很高兴见到你。有什么我可以帮助你的吗？"
        if "叫什么" in last_user or "姓名" in last_user:
            # Look at history for self-introduction
            for m in messages:
                if m.get("role") == "user" and ("我叫" in m.get("content", "") or "我是" in m.get("content", "")):
                    text = m.get("content", "")
                    for prefix in ["我叫", "我是", "我叫做"]:
                        if prefix in text:
                            name = text.split(prefix)[-1].strip().split()[0] if text.split(prefix)[-1].strip() else ""
                            if name:
                                return f"你叫{name}。"
            return "抱歉，我没有从历史中找到您的名字信息。"
        if "天气" in last_user:
            return "正在为您查询天气信息..."
        if "产品" in last_user or "多少钱" in last_user or "功能" in last_user:
            return "根据知识库信息，Context Pilot 是一款用于演示 LLM 上下文管理的开源教学项目，完全免费。它具备 Context 结构可视化、Cache 命中展示、Token 趋势图、窗口溢出策略对比等功能。"
        if "?" in last_user or "？" in last_user:
            return f"这是一个很好的问题。关于「{last_user[:20]}」，我需要更多信息来给您准确的回答。"
        return f"我已收到您的消息: 「{last_user[:30]}」。这是模拟回复，请在设置中配置 LLM API Key 以使用真实模型。"


# Global LLM client
llm_client = LLMClient()
