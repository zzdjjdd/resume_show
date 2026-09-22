# AI 智行助手 v5 · Travel Assistant

端云协同的智能出行助手（多页版）：**行程规划** + **流式聊天** + **可插拔 MCP 工具**。

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](backend/requirements.txt)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## 能做什么

- **旅游模式**：输入目的地与天数生成 Markdown 行程，历史行程落盘保存、可回看。
- **聊天模式**：SSE 流式对话，模型自动调用高德 MCP 工具（地理编码 / POI 搜索 / 路径规划 / 天气）。
- **通用 MCP 客户端**：不绑定特定厂商，填任意 MCP server URL 即可接入新工具（`mcp` / `mcp2` 两个槽位）。
- **在线配置**：LLM、高德、MCP 都能在「设置」页配置并一键测试连通性。

## 快速开始

```bash
# 1) 装依赖
pip install -r backend/requirements.txt

# 2) 配置（二选一）
cp data/config.example.yaml data/config.yaml   # 手动填写
#    或者：启动后在「设置」页面填写，会自动写入 data/config.yaml

# 3) 启动
start.bat            # Windows：双击即可
# 或手动：
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
# 浏览器打开 http://127.0.0.1:8000/
```

`data/config.yaml` 含明文密钥，**已被 `.gitignore` 排除，不要提交**。
结构见 [`data/config.example.yaml`](data/config.example.yaml)。

## 页面

| 路径 | 页面 |
|---|---|
| `/` | 首页 |
| `/plan` | 新建行程 |
| `/plan-detail` | 行程详情 |
| `/chat` | 聊天 |
| `/config` | 设置 |

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` / `POST` | `/api/config`、`/api/config/{llm,amap,mcp,mcp2}` | 配置读写 |
| `POST` | `/api/test/{llm,amap,mcp}` | 连通性测试 |
| `GET` | `/api/mcp/tools` · `POST` `/api/mcp/refresh` · `/api/mcp/call` | MCP 工具发现与调用 |
| `POST` | `/api/llm/models` | 拉取可用模型列表 |
| `POST` / `GET` | `/api/travel/plan` · `/api/travel/plans` · `/api/travel/plan/{id}` | 行程生成与查询 |
| `POST` | `/api/chat` · `/api/chat/stream` | 对话（流式 SSE） |
| `GET` | `/api/health` | 健康检查 |

## 项目结构

```
.
├── backend/
│   ├── app.py              # FastAPI 入口与路由
│   ├── config_store.py     # YAML 配置读写
│   ├── llm_client.py       # OpenAI 兼容 LLM 客户端
│   ├── amap_mcp.py         # 高德 MCP 工具封装
│   ├── mcp_client.py       # 通用 MCP 客户端（JSON-RPC over HTTP）
│   ├── chat_agent.py       # 聊天 Agent 与工具调用循环
│   └── travel_planner.py   # 行程生成
├── frontend/               # 5 个页面 + 共享 CSS/JS
├── data/config.example.yaml
├── docs/                   # MCP 使用说明、启动说明
├── plans/                  # 生成的历史行程（运行时生成）
├── tests/mock_mcp_server.py# 本地 mock MCP server，便于离线调试
└── LICENSE
```

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI 0.115 + Uvicorn + httpx |
| 配置 | PyYAML |
| LLM | 任意 OpenAI 兼容接口（默认 DeepSeek） |
| 工具 | 高德 MCP + 任意外部 MCP server |
| 前端 | 原生 HTML / CSS / JS，Neo-Brutalism 风格，marked.js 渲染 Markdown |

## 离线调试

不想连真实 MCP server 时，可以起本地 mock：

```bash
python tests/mock_mcp_server.py
# 然后在「设置」页把 MCP URL 指向该 mock 地址
```

## License

[MIT](LICENSE) © 2026 zzdjjdd
