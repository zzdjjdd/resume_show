"""配置管理：读写本地 YAML 配置文件"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any
from threading import Lock

CONFIG_DIR = Path(__file__).resolve().parent.parent / "data"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

_lock = Lock()

DEFAULT_CONFIG: Dict[str, Any] = {
    "llm": {
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "timeout": 60,
    },
    "amap": {
        "api_key": "",
        "sse_url": "https://mcp.amap.com/v1/sse",
    },
    "mcp": {
        # 可选：自定义 MCP 服务器 URL(使用 SSE/HTTP 传输)
        "server_url": "",
        # 是否启用 MCP;默认关闭,用户需在设置页勾选
        "enabled": False,
        # MCP 请求超时(秒)
        "timeout": 30,
    },
    # 第二个外部 MCP 服务(服务 2):结构同 mcp。
    # 目前仅支持保存与连接测试;接入聊天 Agent 的工具聚合为后续工作。
    "mcp2": {
        "server_url": "",
        "enabled": False,
        "timeout": 30,
    },
    "ui": {
        "theme": "auto",  # light | dark | auto
    },
}


def ensure_config_dir() -> None:
    """确保配置目录存在"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> Dict[str, Any]:
    """读取配置；如果不存在则返回默认值"""
    ensure_config_dir()
    if not CONFIG_FILE.exists():
        return _deep_copy(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
    except Exception:
        return _deep_copy(DEFAULT_CONFIG)
    return _merge(DEFAULT_CONFIG, user_cfg)


def save_config(cfg: Dict[str, Any]) -> None:
    """写入配置文件"""
    ensure_config_dir()
    with _lock:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)


def _deep_copy(d: Dict[str, Any]) -> Dict[str, Any]:
    """浅深组合拷贝，避免污染默认配置"""
    import copy
    return copy.deepcopy(d)


def _merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并配置字典"""
    result = _deep_copy(base)
    for key, value in (overrides or {}).items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result
