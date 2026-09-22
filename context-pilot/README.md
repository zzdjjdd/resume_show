# Context Pilot - 上下文领航员

🚀 一个用于演示和教学 LLM 上下文管理（Context Engineering）的交互式系统。

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](backend/requirements.txt)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> **不需要任何 API Key 也能完整跑通** —— 演示模式用模拟数据展示缓存命中、
> 窗口溢出策略与 RAG 检索的全过程。想接真实模型再填 Key 即可。

---

## 📖 目录

- [快速开始](#快速开始)
- [功能介绍](#功能介绍)
- [操作指南](#操作指南)
- [配置说明](#配置说明)
- [常见问题](#常见问题)
- [项目结构](#项目结构)
- [技术栈](#技术栈)

---

## 🚀 快速开始

### 启动项目

**方法 A：双击启动**
```
双击 start.bat
```

**方法 B：命令行启动（推荐，可看到日志）**
```bash
# Win+R 输入 cmd 回车
cd /d D:\Desk\项目\context-pilot
start.bat
```

启动成功后会显示：
```
========================================
   服务地址:
     http://localhost:8000
     http://127.0.0.1:8000
   关闭此窗口即可停止服务
========================================
```

**Linux / Mac:**
```bash
chmod +x start.sh
./start.sh
```

### 访问界面

浏览器打开：
```
http://127.0.0.1:8000
```

> 💡 **强烈建议使用 `127.0.0.1` 而不是 `localhost`**，避免某些代理配置干扰。

### 关闭服务

**直接关闭 start.bat 窗口** 即可停止服务。

---

## ✨ 功能介绍

### 🎬 两种工作模式

| 模式 | 用途 | 是否需要 API Key |
|------|------|-----------------|
| **演示模式** | 3 阶段引导式演示（缓存/溢出/RAG+工具） | ❌ 不需要（用模拟数据） |
| **聊天模式** | 实机对话 + 真实 LLM | ✅ 需要配置 LLM |

**演示三阶段：**
1. **第一阶段（5分钟）**：展示基础缓存能力（⚡ CACHE 命中 / 🔄 RECALC 未命中）
2. **第二阶段（5分钟）**：展示窗口溢出处理（删除/摘要/裁剪三种策略对比）
3. **第三阶段（3分钟）**：展示 Context 透明化（RAG + 工具调用）

### 📊 三大核心展示区

1. **左侧聊天区** — 对话气泡 + Token 进度条（绿/橙/红警告）
2. **右侧 Context 结构面板** — System Prompt / 对话历史 / RAG / 工具调用 实时可视化
3. **底部控制台** — 手动触发删除/摘要/裁剪策略

### ⚠️ 窗口警告机制
- 🟢 绿色 (< 80%): 正常
- 🟠 橙色 (80-95%): 警告
- 🔴 红色闪烁 (≥ 95%): 危险
- ⚠️ 超过 100%: 自动弹窗选择策略

---

## 🎮 操作指南

### 演示模式

切换到「🎬 演示模式」，依次点击「下一步」：

**阶段 1 - 缓存演示：**
```
Step 1: 输入「你好，我叫李明」→ 🔄 RECALC (Cache Miss)
Step 2: 输入「我叫什么名字？」→ ⚡ CACHE (Cache Hit)
```

**阶段 2 - 溢出处理：**
```
连续输入长文本 → 进度条 100% → 弹窗选择策略
  🗑️ 删除: 简单粗暴，丢失信息
  📝 摘要: 保留意图，丢失细节
  🎯 裁剪: 保留关键信息（推荐）
```

**阶段 3 - RAG + 工具：**
```
Step 1: 输入「这个产品多少钱？」→ 触发 RAG，右侧显示检索结果
Step 2: 输入「帮我查一下北京的天气」→ 触发工具，右侧显示调用记录
```

### 聊天模式

直接输入消息按 Enter 发送。自动触发的关键词：

| 输入 | 触发 |
|------|------|
| 包含「天气」+ 城市 | 调用高德地图天气工具 |
| 包含「怎么走」「开车」 | 调用路径规划 |
| 包含「产品」「多少钱」「功能」 | 触发 RAG 检索 |
| 重复相同问题 | 显示 Cache 命中（绿色字体） |

---

## ⚙️ 配置说明

点击右上角 ⚙️ 打开设置。

### 🤖 大模型配置

| 字段 | 说明 | 示例 |
|------|------|------|
| Base URL | API 端点 | `https://api.deepseek.com` / `https://api.minimaxi.com/v1` |
| API Key | 您的密钥 | `sk-xxxxxxxx` |
| 模型名称 | 具体模型 | `deepseek-chat` / `MiniMax-M3` |
| Temperature | 创造性 (0-2) | `0.7` |

**点击「🔌 测试连接」验证配置**

### 📐 Embedding 配置（可选）

不配置也能用，会降级到关键词检索。

| 字段 | 默认 |
|------|------|
| Base URL | `https://api.siliconflow.cn/v1` |
| 模型 | `Qwen/Qwen3-Embedding-4B` |

### 🔌 MCP 服务（可选）

不配置也能用，使用模拟数据展示。

| 字段 | 说明 |
|------|------|
| MCP URL | 高德地图 MCP 端点 |
| API Key | 高德地图 API Key |

### 📊 上下文窗口

默认 2048 Token，范围 512-32000。修改后立即生效。

### 配置文件位置

所有配置持久化在 `data/settings.json`，可手动编辑。
该文件含明文密钥，**已被 `.gitignore` 排除**；结构模板见
[`data/settings.example.json`](data/settings.example.json)。

---

## ❓ 常见问题

### Q: 双击 start.bat 窗口一闪而过？
**原因**：启动失败（Python 未装/依赖缺失/端口占用）
**解决**：
```bash
cd /d D:\Desk\项目\context-pilot
start.bat
```
用命令行运行看错误。

### Q: 浏览器显示「拒绝连接」？
**排查：**
1. 检查 start.bat 窗口是否还开着
2. `curl http://127.0.0.1:8000/` 本机测试
3. 端口被占用 → start.bat 自动切换到 8001

### Q: 控制台报「Failed to fetch」？
**原因**：CORS 跨域（已内置修复）。如出现：重启服务 + 浏览器 `Ctrl+F5` 强制刷新。

### Q: API Key 测试连接失败？

| 错误 | 原因 | 解决 |
|------|------|------|
| `401 Authentication Fails` | Key 无效 | 重新生成 |
| `429 Rate Limit` | 请求过快 | 稍后重试 |
| `Network timeout` | 网络问题 | 检查代理/防火墙 |

### Q: 端口 8000 被占用？
```bash
netstat -ano | findstr ":8000"  # 查看占用
# 或让 start.bat 自动切换到 8001
```

### Q: 修改了代码不生效？
FastAPI 默认 `--reload` 没启用，需要重启 start.bat。

### Q: 想换默认端口？
编辑 `start.bat` 中的 `set PORT=8000` 改值。

---

## 📁 项目结构

```
D:\Desk\项目\context-pilot\
├── backend/                  # 后端
│   ├── main.py              # FastAPI 主应用（含 CORS）
│   ├── context_manager.py   # 上下文管理 + 缓存 + 策略
│   ├── rag.py               # RAG 知识库
│   ├── mcp_client.py        # MCP 客户端
│   ├── llm_client.py        # LLM 客户端
│   └── requirements.txt     # Python 依赖
│
├── frontend/                # 前端
│   ├── templates/index.html
│   └── static/
│       ├── styles.css       # 亮色渐变样式
│       └── app.js
│
├── data/
│   └── settings.json        # 用户配置
│
├── start.bat                # Windows 启动
├── start.sh                 # Linux/Mac 启动
└── 提示词.md                # 原始需求
```

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | HTML + CSS + JavaScript (原生) |
| 后端 | FastAPI + Uvicorn |
| RAG | LangChain + FAISS |
| Embedding | SiliconFlow (Qwen3-Embedding-4B) |
| LLM | OpenAI 兼容 API (DeepSeek / MiniMax 等) |
| MCP | 高德地图 MCP |

---

## 💡 小贴士

1. **首次启动**自动装依赖（1-2 分钟），之后秒开
2. **演示模式**不需 API Key，完整可跑
3. **聊天模式**至少配 LLM Key
4. **数据持久化**在 `data/` 目录，删除会重置
5. **修改代码**后重启服务才生效

---

## 🔗 相关链接

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [LangChain 文档](https://python.langchain.com/)
- [MCP 协议](https://modelcontextprotocol.io/)

---

## 📄 License

[MIT](LICENSE) © 2026 zzdjjdd
