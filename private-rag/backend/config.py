"""加载 .env 并集中暴露所有配置。"""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# 1) 加载 .env(项目根目录)
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


class Settings:
    # ===== Embedding (硅基流动) =====
    SILICONFLOW_API_KEY: str = os.getenv("SILICONFLOW_API_KEY", "")
    SILICONFLOW_BASE_URL: str = os.getenv(
        "SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"
    )
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-4B")

    # ===== LLM (MiniMax) =====
    MINIMAX_API_KEY: str = os.getenv("MINIMAX_API_KEY", "")
    MINIMAX_BASE_URL: str = os.getenv(
        "MINIMAX_BASE_URL", "https://api.minimaxi.com/v1"
    )
    LLM_MODEL: str = os.getenv("LLM_MODEL", "MiniMax-M3")

    # ===== 服务 =====
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))

    # ===== 分块与检索 =====
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "80"))
    TOP_K: int = int(os.getenv("TOP_K", "4"))

    # ===== 路径 =====
    DATA_DIR: Path = ROOT / os.getenv("DATA_DIR", "data")
    INDEX_DIR: Path = ROOT / os.getenv("INDEX_DIR", "storage")
    LOG_DIR: Path = ROOT / "logs"
    UPLOAD_DIR: Path = ROOT / "data" / "uploads"

    @classmethod
    def ensure_dirs(cls) -> None:
        for p in (cls.DATA_DIR, cls.INDEX_DIR, cls.LOG_DIR, cls.UPLOAD_DIR):
            p.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()