"""环境与路径配置。

参考原 NestJS 的 main.ts 与 llm/interview-provider.config.ts。
保持 INTERVIEW_* / DASHSCOPE_* / OPENAI_* 环境变量语义一致，方便复用原 .env。
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# ---- 项目根目录 ----
# app/config.py 位于 backend/app/ 下，backend 在 app 的上一级
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

# 优先加载根目录 .env，其次 backend/.env（兼容原实现：从 cwd 向上查找）
_loaded = False


def _load_env_once() -> None:
    global _loaded
    if _loaded:
        return
    candidates = [
        PROJECT_ROOT / ".env",
        PROJECT_ROOT / ".env.local",
        BACKEND_DIR / ".env",
    ]
    for candidate in candidates:
        if candidate.exists():
            load_dotenv(dotenv_path=str(candidate), override=False)
            break
    _loaded = True


_load_env_once()

# ---- 数据与 Schema 路径 ----
DATA_DIR = PROJECT_ROOT / "data"
RESUME_FILES_PATH = Path(
    os.environ.get("RESUME_FILES_PATH", str(DATA_DIR / "resume-files.json"))
)
RESUME_FILES_EXAMPLE_PATH = DATA_DIR / "resume-files.example.json"
RESUME_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "resume.schema.json"

# 首次运行无数据文件时，用示例或种子初始化
DEFAULT_RESUME_FILES = str(RESUME_FILES_PATH)

# ---- LLM Provider 配置（兼容原 .env 语义）----


def first_env(names: list[str]) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value and value.lower() not in ("none", "null"):
            return value
    return ""


def parse_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False
    return None


@lru_cache(maxsize=None)
def resolve_interview_api_key() -> str:
    return first_env(
        ["INTERVIEW_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY"]
    ).strip()


@lru_cache(maxsize=None)
def resolve_interview_base_url() -> str:
    return first_env(
        [
            "INTERVIEW_BASE_URL",
            "DASHSCOPE_BASE_URL",
            "OPENAI_BASE_URL",
        ]
    ).strip() or "https://api.openai.com/v1"


@lru_cache(maxsize=None)
def resolve_interview_model() -> str:
    return (
        first_env(
            ["INTERVIEW_MODEL", "DASHSCOPE_MODEL", "OPENAI_MODEL"]
        ).strip()
        or "gpt-4o-mini"
    )


@lru_cache(maxsize=None)
def resolve_interview_enable_thinking() -> bool | None:
    """Deep Interview 需要结构化 JSON，兼容接口默认关闭 thinking。"""
    base = resolve_interview_base_url().lower()
    explicit = first_env(
        [
            "INTERVIEW_ENABLE_THINKING",
            "INTERVIEW_LLM_ENABLE_THINKING",
            "DASHSCOPE_ENABLE_THINKING",
        ]
    )
    parsed = parse_bool(explicit)
    if parsed is not None:
        return parsed
    if (
        "dashscope.aliyuncs.com/compatible-mode" in base
        or ".maas.aliyuncs.com/compatible-mode" in base
    ):
        return False
    return None


def has_llm_provider() -> bool:
    return bool(resolve_interview_api_key())


# ---- 深度面试 Agent 预算（兼容 .env）----


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


@lru_cache(maxsize=None)
def agent_config() -> dict:
    return {
        "maxSearchRounds": env_int("INTERVIEW_AGENT_MAX_SEARCH_ROUNDS", 3),
        "maxPages": env_int("INTERVIEW_AGENT_MAX_PAGES", 20),
        "prepareLlmLimit": env_int("INTERVIEW_AGENT_PREPARE_LLM_LIMIT", 15),
        "turnLlmLimit": env_int("INTERVIEW_AGENT_TURN_LLM_LIMIT", 4),
        "sessionLlmLimit": env_int("INTERVIEW_AGENT_SESSION_LLM_LIMIT", 80),
        "maxFollowUp": env_int("INTERVIEW_AGENT_MAX_FOLLOW_UP", 2),
        "coverageThreshold": float(
            os.environ.get("INTERVIEW_AGENT_COVERAGE_THRESHOLD", "0.8")
        ),
        "llmTimeoutMs": env_int("INTERVIEW_AGENT_LLM_TIMEOUT_MS", 120000),
    }
