"""一键启动脚本。"""
from __future__ import annotations

import os
import sys
import uvicorn
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backend.config import settings  # noqa: E402


def main():
    print(f"\n>>> 点头 RAG 本地知识库")
    print(f">>> Embedding: {settings.EMBEDDING_MODEL}")
    print(f">>> LLM      : {settings.LLM_MODEL}")
    print(f">>> 浏览器打开 http://{settings.HOST}:{settings.PORT}/\n")

    uvicorn.run(
        "backend.app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()