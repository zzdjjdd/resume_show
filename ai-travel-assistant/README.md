# AI 智行助手 · AI Travel Assistant

端云协同的智能出行助手：**行程规划** + **日常问答**，由 LLM 驱动并自动调用高德地图等 MCP 工具。

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](backend/requirements.txt)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## 能做什么

| 模式 | 说明 |
|---|---|
| **旅游模式** `/api/travel/plan` | 输入目的地与天数，生成 Markdown 行程（景点 / 餐饮 / 交通 / 住宿） |
| **聊天模式** `/api/chat` | 流式 SSE 对话，模型自行决定是否调用工具，最多 5 轮 ReAct 工具调用 |

内置工具（通过高德 Web 服务 API）：

- 地理编码 / 逆地理编码
- POI 与周边搜索（酒店、景点、餐饮）
- 路径规划（步行 / 骑行 / 驾车 / 公交）
- 天气查询、距离测量

另外支持接入**任意外部 MCP server**（如 12306 车次、酒店查询），在「设置」页填 URL 即可。

## 快速开始

```bash
# 1) 装依赖
pip install -r backend/requirements.txt

# 2) 配置凭据（二选一）
cp backend/config.example.json backend/config.json   # 手动填写
#    或者：启动后在「设置」页面填写并点「测试连接」，会自动写入 config.json

# 3) 启动
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --app-dir .
# 浏览器打开 http://localhost:8000/
```

`backend/config.json` 含明文密钥，**已被 `.gitignore` 排除，不要提交**。

> 详细的 conda 环境 / 依赖版本 / 已知坑位见 [`启动说明.md`](启动说明.md)。

## 配置项

`backend/config.json` 结构见 [`backend/config.example.json`](backend/config.example.json)：

| 字段 | 说明 |
|---|---|
| `llm.api_key` / `base_url` / `model` | OpenAI 兼容的对话模型，默认 `MiniMax-M3` |
| `amap.api_key` | 高德**「Web 服务」**Key（不是「Web 端 JS API」Key） |
| `mcp.servers[]` | 外部 MCP server 列表，每项含 `name` / `url` / `enabled` |

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` / `POST` | `/api/config` | 读取 / 写入配置 |
| `POST` | `/api/test/llm` · `/api/test/amap` · `/api/test/mcp` | 连通性测试 |
| `POST` | `/api/travel/plan` | 生成行程 |
| `POST` | `/api/chat` | SSE 流式对话（事件合约见 [`rules/02-SSE协议与事件合约.md`](rules/02-SSE协议与事件合约.md)） |
| `GET` | `/` | 前端页面 |

## 项目结构

```
.
├── backend/
│   ├── main.py            # FastAPI 入口与路由
│   ├── ai_service.py      # LLM 调用与工具编排（ReAct）
│   ├── amap_service.py    # 高德 Web 服务 API 封装
│   ├── mcp_client.py      # 通用 MCP 客户端
│   ├── config.py          # 配置读写
│   └── config.example.json
├── frontend/
│   ├── index.html
│   ├── js/app.js
│   └── css/styles.css     # aurora 极光渐变主题
├── rules/                 # 工程约束文档（01-08）
├── 启动说明.md
├── AGENTS.md / CLAUDE.md  # 给 AI 协作者的上下文说明
└── LICENSE
```

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI 0.110 + Uvicorn |
| LLM | `openai` SDK 1.13.3（OpenAI 兼容协议） |
| 工具 | 高德 Web 服务 API + Model Context Protocol |
| 前端 | 原生 HTML / CSS / JavaScript，单页应用 |

## 开发约束

改代码前请先读 [`rules/`](rules/README.md)，其中 `05-改代码硬约束.md` 与
`06-禁止事项.md` 记录了几条必须遵守的约定，`08-已知坑位.md` 记录了踩过的坑
（例如 openai 1.13.3 与 httpx 0.28+ 的 `proxies` 参数冲突，已在
`_build_http_client` 中绕过，**不要**随意升级 openai）。

## License

[MIT](LICENSE) © 2026 zzdjjdd
