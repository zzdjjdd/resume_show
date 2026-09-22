# MCP 工具接入使用说明

> 适用版本:v5(2026-07-25 新增)

## 一、能做什么

v5 已支持**接入任意标准 MCP server**。LLM 在聊天时会自动发现 server 声明的工具,并在需要时调用,无需改代码。

适用场景:
- 12306 高铁票查询
- 酒店/民宿查询
- 任何官方/自部署的 MCP 服务(Anthropic 协议兼容)

UI 路径:`设置 → ③ 外部 MCP 服务`,输入 `server URL` + 勾选启用,**重启后端**生效。

## 二、已验证

| 端点 | 状态 | 说明 |
| --- | --- | --- |
| 本地 mock server (tests/mock_mcp_server.py) | ✅ 通过 | 端到端 verify:initialize → list_tools → call_tool → summary,全链路 OK |
| ModelScope 12306-mcp v1.9.4 | ⚠️ 服务端 bug | `initialize` 200 OK 拿到 `serverInfo: {name: "12306-mcp", version: "1.9.4"}`;但 `tools/list` 任何 params 形式都返回 `-32602 Invalid request parameters` —— **服务端实现有缺陷**。需要服务端修复或换其他 server。 |

## 三、当前使用建议

由于 12306-mcp v1.9.4 的 `tools/list` 不可用,**立即能用的方案**:

1. **换其他健康的 MCP server**(先用接入方法验证)
2. **本地起 mock 测试**:见下方
3. **如果你的酒店查询是另一个独立 URL**:在设置中填入**第二个 MCP server URL** 字段(当前 v5 只支持 1 个 mcp 段,需要你确认后再加段位)

### 本地起 mock server 测试(已实现)

```bash
# 终端 A:启动 mock MCP
cd D:\Desk\项目\travel-assistant-v5
python -m tests.mock_mcp_server
# 监听 127.0.0.1:18765,暴露 get_weather + search_train 两个工具

# 终端 B:启动 v5 后端
python -m backend.app

# 浏览器 http://localhost:8765/config
# ③ 外部 MCP 服务:
#   URL: http://127.0.0.1:18765
#   超时: 10
#   启用: ✓
# 点"测试连接" → 应看到"已加载 2 个工具"
# 点"保存 MCP 配置" → 重启后端,启动日志应打印 [mcp] 已加载 2 个工具 ...

# 浏览器 http://localhost:8765/chat
# 输入:"查一下北京天气" → 聊天流出现 mc_get_weather 卡片
# 输入:"查一下北京到上海的高铁" → 出现 mc_search_train 卡片,带 3 趟车次
```

## 四、协议兼容性

`MCPClient` 实现的兼容范围:
- ✅ JSON-RPC 2.0 over HTTP(`Content-Type: application/json`)
- ✅ 流式响应 `text/event-stream`,自动解析最后一条 `data:` 行
- ✅ `mcp-session-id` 协议:`initialize` 响应头 `mcp-session-id` 自动保存,后续请求带 `Mcp-Session-Id`
- ✅ 标准 schema 映射:MCP `inputSchema` → OpenAI `parameters`
- ❌ 不支持 stdio 传输(MCP 协议另一形态,需要子进程)

## 五、故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 设置页 "测试连接" → ok:false,error: "MCP 未启用或未初始化" | 配置没启用 / 没重启 | 设置中勾选"启用" + 保存 + **重启后端** |
| error: "initialize error: ..." | URL 不可达或非 MCP 服务 | 用浏览器/curl 直访问 URL,确认返回 JSON-RPC |
| error: "tools/list error: ..." | **服务端 bug**(见 12306 案例) | 换 server;或向 12306-mcp 提 issue |
| 启动日志有 `[mcp] 初始化失败: ...` 但应用仍启动 | 已优雅降级 | 检查 stderr 日志,fix URL 后再启 |
| chat 页看到 `mc_*` 卡片但 summary 显示 "MCP 未启用" | 重启前的旧 app.state | 强制重启后端 |

## 六、文件变更清单(本次)

```
新增:
  backend/mcp_client.py          通用 MCPClient(JSON-RPC 2.0 + SSE)
  tests/mock_mcp_server.py       本地 mock server,用于验证

修改:
  backend/config_store.py        mcp 段加 enabled + timeout 字段(默认关)
  backend/chat_agent.py          SYSTEM_PROMPT + mc_ 前缀 + _route_tool/_summarize,max_tool_rounds 4→6
  backend/app.py                 lifespan 启动期 initialize + 4 个新端点 + MCPConfigIn 扩字段
  frontend/config.html           ③ 外部 MCP 服务 卡片
  frontend/assets/js/pages/config.js  4 个 MCP 事件(测试/刷新/保存/启动加载)+ 修全量保存 bug
  CLAUDE.md                      模块表 + API 路由表 + 5.4 外部 MCP 集成 小节
```

## 七、回退

如需回退到原 v5(无 MCP):
1. 设置页把"启用 MCP"取消勾选,**前端**将不再调 MCP 工具
2. 也可手动从 `data/config.yaml` 删除整个 `mcp` 段
3. 重启后端 —— ChatAgent 的 `_route_tool` 见到 `mc_*` 前缀但 `self.mcp is None` 会返回 `{"success": False, "error": "MCP 未启用"}`,不影响 amap 工具
