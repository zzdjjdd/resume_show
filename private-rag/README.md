# Local RAG Knowledge Base · 本地知识库问答

一个可完全跑在本机的 RAG 问答系统：**Qwen3-Embedding-4B + FAISS + MiniMax-M3**。
支持上传 PDF / Word / TXT / Markdown 建库，带引用来源标注与「是否需要查知识库」的路由判断。

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](requirements.txt)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## 特性

- **纯本地检索**：向量索引落在本机 FAISS，文档不出内网；只有问答请求会发往模型 API。
- **多格式入库**：`.pdf` / `.docx` / `.txt` / `.md`，段落优先分块 + 滑窗兜底。
- **引用可追溯**：回答附带命中的原文片段与来源文档，便于核对。
- **智能路由**：闲聊类问题不查库，知识类问题才触发检索，省 token 也更快。
- **零构建前端**：原生 HTML/CSS/JS，无 npm、无打包步骤。

## 快速开始

```bash
# 1) 装依赖
pip install -r requirements.txt

# 2) 配置密钥
cp .env.example .env        # Git Bash / macOS / Linux
copy .env.example .env      # Windows CMD
#    然后编辑 .env 填入 SILICONFLOW_API_KEY 与 MINIMAX_API_KEY

# 3) 启动
python run.py
# 浏览器打开 http://127.0.0.1:8000/
```

**建库的两种方式**（二选一或都用）：

- 页面上点「上传文档」，即时解析入库；
- 把文件丢进 [`data/seed/`](data/seed/)，**首次启动自动入库**。

> 本仓库不附带任何真实业务文档。`data/seed/` 为空也能正常启动，只是知识库为空。

## 配置项

全部通过 `.env` 注入，完整清单见 [`.env.example`](.env.example)：

| 变量 | 说明 | 默认 |
|---|---|---|
| `SILICONFLOW_API_KEY` | 硅基流动 Key（嵌入模型） | 必填 |
| `EMBEDDING_MODEL` | 嵌入模型名 | `Qwen/Qwen3-Embedding-4B` |
| `MINIMAX_API_KEY` | MiniMax Key（对话模型） | 必填 |
| `LLM_MODEL` | 对话模型名 | `MiniMax-M3` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 分块大小 / 重叠 | `500` / `80` |
| `TOP_K` | 检索返回条数 | `4` |
| `INDEX_DIR` | 索引落盘目录 | `./storage` |

`.env` 已被 `.gitignore` 排除，**不要提交真实密钥**。

## 项目结构

```
.
├── backend/                 # FastAPI 后端
│   ├── app.py               # 入口：REST API + 静态前端 + 启动自动入库
│   ├── config.py            # 读取 .env
│   ├── loaders.py           # PDF / DOCX / TXT / MD 解析
│   ├── splitter.py          # 段落优先分块 + 滑窗
│   ├── embedder.py          # Qwen3-Embedding-4B 调用
│   ├── vectorstore.py       # FAISS 索引（单例）
│   ├── llm.py               # MiniMax-M3 调用
│   ├── rag.py               # RAG 主流程 + 查库路由判断
│   └── schemas.py           # Pydantic 模型
├── frontend/                # 原生 HTML/CSS/JS 前端
├── data/seed/               # 启动自动入库的种子文档
├── storage/                 # FAISS 索引与元数据（运行时生成）
├── logs/                    # 运行日志（运行时生成）
├── .env.example             # 环境变量模板
├── requirements.txt
└── run.py                   # 一键启动
```

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + Uvicorn |
| 分块 | LangChain Text Splitters |
| 向量检索 | FAISS（IndexFlatIP + L2 归一化 ≈ 余弦相似度） |
| 嵌入 | Qwen3-Embedding-4B（硅基流动） |
| 生成 | MiniMax-M3（OpenAI 兼容协议） |
| 前端 | 原生 HTML / CSS / JavaScript |

## 说明

- 元数据用 pickle + JSON 落盘（`storage/_faiss.index`、`metadata.pkl`、`docs.json`），
  删除 `storage/` 即清空知识库。
- `INDEX_DIR` 建议使用**纯 ASCII 路径**：FAISS 在含中文的路径下 `fopen` 可能失败。

## License

[MIT](LICENSE) © 2026 zzdjjdd
