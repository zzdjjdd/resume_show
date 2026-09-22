"""
Context management module
- Token counting (approximate)
- KV Cache simulation
- Window overflow strategies: delete, summary, trim
- Context structure tracking
"""
import re
import hashlib
from typing import List, Dict, Any, Tuple


def count_tokens(text: str) -> int:
    """Approximate token count: ~1 token per 1.5 Chinese chars or 0.75 English words"""
    if not text:
        return 0
    # Count Chinese characters
    chinese_chars = len(re.findall(r'[一-鿿]', text))
    # Count English words
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    # Count numbers/punctuation
    others = len(re.findall(r'[\d\s\W]', text))
    return int(chinese_chars * 0.7 + english_words * 1.3 + others * 0.5)


def count_messages_tokens(messages: List[Dict[str, str]]) -> int:
    """Count tokens for a list of messages"""
    total = 0
    for msg in messages:
        content = msg.get('content', '')
        if isinstance(content, str):
            total += count_tokens(content)
        else:
            total += count_tokens(str(content))
        # Overhead for role
        total += 4
    return total


def get_content_hash(content: str) -> str:
    """Generate a hash for content to use as cache key"""
    return hashlib.md5(content.encode('utf-8')).hexdigest()[:16]


class ContextManager:
    """Manages the context window, cache, and overflow strategies"""

    def __init__(self, max_tokens: int = 2048):
        self.max_tokens = max_tokens
        self.system_prompt = ""
        self.messages: List[Dict[str, Any]] = []  # Each has role, content, tokens, cache_hit
        self.rag_results: List[Dict[str, Any]] = []  # RAG retrieved context
        self.tool_calls: List[Dict[str, Any]] = []  # Tool call records
        self.cache_hits = 0
        self.cache_misses = 0
        self.token_history: List[Dict[str, Any]] = []
        # Cache: key -> response, supports prefix matching
        self.response_cache: Dict[str, str] = {}
        self._system_prompt_tokens = 0

    def set_system_prompt(self, prompt: str):
        self.system_prompt = prompt
        self._system_prompt_tokens = count_tokens(prompt)

    def add_message(self, role: str, content: str) -> Dict[str, Any]:
        """Add a message and determine if it hit cache"""
        msg_tokens = count_tokens(content)
        # Cache check: if exact same question in history, hit
        cache_key = get_content_hash(content)
        cache_hit = cache_key in self.response_cache

        msg = {
            "role": role,
            "content": content,
            "tokens": msg_tokens,
            "cache_hit": cache_hit,
            "cache_key": cache_key
        }
        self.messages.append(msg)

        if role == "user":
            if cache_hit:
                self.cache_hits += 1
            else:
                self.cache_misses += 1

        self._record_token_state()
        return msg

    def add_assistant_message(self, content: str, cache_hit: bool = False) -> Dict[str, Any]:
        """Add an assistant message (the response)"""
        msg_tokens = count_tokens(content)
        msg = {
            "role": "assistant",
            "content": content,
            "tokens": msg_tokens,
            "cache_hit": cache_hit
        }
        self.messages.append(msg)
        # Save to cache for future hit detection
        if not cache_hit:
            # Cache the most recent user-assistant pair
            user_msg = None
            for m in reversed(self.messages[:-1]):
                if m["role"] == "user":
                    user_msg = m
                    break
            if user_msg:
                self.response_cache[user_msg["cache_key"]] = content
        self._record_token_state()
        return msg

    def add_rag_result(self, query: str, docs: List[Dict[str, Any]]):
        """Add RAG retrieval results to context"""
        content = "\n".join([f"[知识库片段 {i+1}]: {d.get('content', d.get('text', str(d)))}" for i, d in enumerate(docs)])
        self.rag_results.append({
            "query": query,
            "content": content,
            "docs": docs,
            "tokens": count_tokens(content)
        })

    def add_tool_call(self, tool_name: str, args: Dict, result: Any):
        """Add a tool call record to context"""
        record = {
            "tool": tool_name,
            "args": args,
            "result": result,
            "tokens": count_tokens(f"调用工具: {tool_name}({args}) -> {str(result)[:200]}")
        }
        self.tool_calls.append(record)

    def get_current_tokens(self) -> int:
        """Get current total token count"""
        msg_tokens = sum(m["tokens"] for m in self.messages)
        rag_tokens = sum(r["tokens"] for r in self.rag_results)
        tool_tokens = sum(t["tokens"] for t in self.tool_calls)
        return self._system_prompt_tokens + msg_tokens + rag_tokens + tool_tokens

    def get_usage_percent(self) -> float:
        return self.get_current_tokens() / self.max_tokens * 100

    def get_context_structure(self) -> Dict[str, Any]:
        """Return breakdown of context structure for visualization"""
        msg_tokens = sum(m["tokens"] for m in self.messages)
        rag_tokens = sum(r["tokens"] for r in self.rag_results)
        tool_tokens = sum(t["tokens"] for t in self.tool_calls)
        total = self.get_current_tokens()
        return {
            "system_prompt": {
                "content": self.system_prompt,
                "tokens": self._system_prompt_tokens,
                "percent": (self._system_prompt_tokens / total * 100) if total else 0
            },
            "history": {
                "count": len(self.messages),
                "tokens": msg_tokens,
                "percent": (msg_tokens / total * 100) if total else 0,
                "messages": self.messages
            },
            "rag": {
                "count": len(self.rag_results),
                "tokens": rag_tokens,
                "percent": (rag_tokens / total * 100) if total else 0,
                "items": self.rag_results
            },
            "tools": {
                "count": len(self.tool_calls),
                "tokens": tool_tokens,
                "percent": (tool_tokens / total * 100) if total else 0,
                "items": self.tool_calls
            },
            "total_tokens": total,
            "max_tokens": self.max_tokens,
            "usage_percent": self.get_usage_percent(),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses
        }

    def _record_token_state(self):
        """Record current token state for the trend chart"""
        self.token_history.append({
            "step": len(self.token_history),
            "tokens": self.get_current_tokens(),
            "usage_percent": self.get_usage_percent()
        })
        # Keep only last 50
        if len(self.token_history) > 50:
            self.token_history = self.token_history[-50:]

    # ============= Strategies for handling window overflow =============

    def strategy_delete(self, keep_last: int = 4) -> Dict[str, Any]:
        """Strategy 1: Delete old history, keep last N messages"""
        if len(self.messages) <= keep_last:
            return {"action": "delete", "removed": 0, "note": "历史过短，无需删除"}
        removed = len(self.messages) - keep_last
        # Keep first system-style message if any, and the last N
        self.messages = self.messages[-keep_last:]
        # Also clear old RAG and tool calls
        self.rag_results = self.rag_results[-2:] if len(self.rag_results) > 2 else []
        self.tool_calls = self.tool_calls[-2:] if len(self.tool_calls) > 2 else []
        return {
            "action": "delete",
            "removed": removed,
            "note": f"已删除 {removed} 条历史消息，保留最近 {keep_last} 条"
        }

    def strategy_summary(self) -> Dict[str, Any]:
        """Strategy 2: Summarize old messages into a single summary message.
        For demo, this is a simple concatenation; in real LLM, would call summary API."""
        if len(self.messages) <= 2:
            return {"action": "summary", "note": "消息过少，无需总结"}
        # Keep last 2 messages, summarize the rest
        to_summarize = self.messages[:-2]
        last_messages = self.messages[-2:]
        summary_text = "[历史摘要] " + " | ".join([
            f"{m['role']}: {m['content'][:50]}{'...' if len(m['content']) > 50 else ''}"
            for m in to_summarize
        ])
        summary_msg = {
            "role": "system",
            "content": summary_text,
            "tokens": count_tokens(summary_text),
            "cache_hit": False,
            "is_summary": True
        }
        self.messages = [summary_msg] + last_messages
        return {
            "action": "summary",
            "summarized_count": len(to_summarize),
            "note": f"已将 {len(to_summarize)} 条历史消息总结为 1 条摘要"
        }

    def strategy_trim(self) -> Dict[str, Any]:
        """Strategy 3: Smart trim - keep important messages (questions, key info)"""
        if len(self.messages) <= 4:
            return {"action": "trim", "note": "消息过少，无需裁剪"}
        # Keep all user messages and last 2 assistant messages
        kept = []
        removed = 0
        for i, msg in enumerate(self.messages):
            if msg["role"] == "user" or i >= len(self.messages) - 2:
                kept.append(msg)
            else:
                removed += 1
        self.messages = kept
        # Trim tool calls and RAG to most recent
        if len(self.tool_calls) > 2:
            removed += len(self.tool_calls) - 2
            self.tool_calls = self.tool_calls[-2:]
        return {
            "action": "trim",
            "removed": removed,
            "note": f"智能裁剪了 {removed} 条次要消息，保留关键问答"
        }

    def reset(self):
        """Reset all context"""
        self.messages = []
        self.rag_results = []
        self.tool_calls = []
        self.cache_hits = 0
        self.cache_misses = 0
        self.token_history = []
        self.response_cache = {}


# Demo scripts: pre-defined demonstration sequences
DEMO_STEPS = {
    "stage1_cache": {
        "title": "第一阶段：展示基础缓存能力",
        "description": "展示上下文缓存命中与未命中的效果",
        "steps": [
            {
                "title": "Step 1: 用户自我介绍 (Cache Miss)",
                "user_input": "你好，我叫李明",
                "expected_response": "你好李明！很高兴认识你。有什么我可以帮助你的吗？",
                "expected_cache_hit": False,
                "note": "第一次对话，Cache Miss，需要重新计算 ⚡"
            },
            {
                "title": "Step 2: 询问姓名 (Cache Hit)",
                "user_input": "我叫什么名字？",
                "expected_response": "你叫李明。",
                "expected_cache_hit": True,
                "note": "直接从Cache中读取上下文，命中 ⚡"
            }
        ]
    },
    "stage2_overflow": {
        "title": "第二阶段：展示窗口溢出处理",
        "description": "模拟窗口填满，并演示三种处理策略",
        "steps": [
            {
                "title": "Step 1: 填充长文本",
                "user_input": "请详细介绍一下人工智能的历史、当前发展以及未来趋势，包括机器学习、深度学习、自然语言处理等各个子领域。",
                "expected_response": "人工智能的发展历程非常悠久，从1956年的达特茅斯会议开始...",
                "note": "长文本会让Token快速上升"
            },
            {
                "title": "Step 2: 继续填充",
                "user_input": "再补充一些关于计算机视觉、强化学习、知识图谱、推荐系统方面的详细信息，包括主要算法、典型应用场景和代表性论文。",
                "expected_response": "计算机视觉是AI的重要分支，包括图像分类、目标检测、分割等任务...",
                "note": "Token继续上升，接近窗口上限"
            },
            {
                "title": "Step 3: 触发窗口溢出",
                "user_input": "再详细讲讲大语言模型的训练流程、Transformer架构、注意力机制的原理以及RLHF的细节。",
                "expected_response": "大语言模型基于Transformer架构...",
                "note": "窗口将达到100%，触发策略选择"
            }
        ]
    },
    "stage3_rag_tool": {
        "title": "第三阶段：展示Context透明化 (RAG + 工具调用)",
        "description": "展示RAG检索和工具调用如何注入到Context中",
        "steps": [
            {
                "title": "Step 1: RAG检索 - 询问产品",
                "user_input": "这个产品多少钱？有什么功能？",
                "expected_response": "根据知识库信息，Context Pilot是一款上下文管理演示系统...",
                "note": "右侧 RAG检索结果 自动展开"
            },
            {
                "title": "Step 2: 工具调用 - 查询天气",
                "user_input": "帮我查一下北京的天气",
                "expected_response": "正在调用高德地图API查询北京天气...",
                "tool_call": {
                    "tool": "get_weather",
                    "args": {"city": "北京"}
                },
                "note": "右侧 工具调用记录 出现 get_weather(city='北京')"
            }
        ]
    }
}
