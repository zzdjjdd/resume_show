"""
配置管理：负责持久化保存用户在前端填写的 LLM / 高德地图 MCP 等参数。
存储为 backend 目录下的 config.json。
"""
import json
import os
from pathlib import Path
from typing import Any, Dict

CONFIG_DIR = Path(__file__).resolve().parent
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    # LLM 相关配置（OpenAI 兼容格式）
    # 当前默认走本地环境的 MiniMax-M3，API Key / Base URL 留空时由 OpenAI() 自动读取环境变量。
    "llm": {
        "api_key": "",
        "base_url": "",
        "model": "MiniMax-M3",
        "reasoning_split": True,
    },
    # 高德地图 MCP 相关配置
    "amap": {
        "sse_url": "",   # 高德 MCP 的 SSE 服务 URL（前端存储）
        "api_key": "",   # 高德开放平台 Web 服务 API Key（后端实际调用高德开放接口时使用）
    },
    # 外部 MCP 服务器（通用 JSON-RPC over SSE 协议）
    # 每个 server 形如 {name, url, enabled}；name 会用作工具名前缀 "{name}__{tool}"
    # 默认预填 12306 / 酒店两条占位；URL 留空表示未启用。
    "mcp": {
        "servers": [
            {"name": "12306", "url": "", "enabled": False},
            {"name": "hotel", "url": "", "enabled": False},
        ],
    },
}


def load_config() -> Dict[str, Any]:
    """读取配置文件，若不存在则使用默认配置。"""
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # 缺失字段补齐
        merged = json.loads(json.dumps(DEFAULT_CONFIG))
        for k, v in (data or {}).items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k].update(v)
            else:
                merged[k] = v
        return merged
    except Exception:
        return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(cfg: Dict[str, Any]) -> None:
    """保存配置到磁盘。"""
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def update_config(section: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """更新某一个 section（llm/amap）的字段。"""
    cfg = load_config()
    if section not in cfg:
        cfg[section] = {}
    cfg[section].update({k: v for k, v in payload.items() if v is not None})
    save_config(cfg)
    return cfg
