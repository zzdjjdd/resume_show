"""FastAPI 入口。

组合各模块路由，并提供健康检查与前端静态托管。
对应原 NestJS 的 app.module.ts / app.controller.ts / main.ts。
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .routers import ai, jobs, resumes
from .routers.jobs import list_jobs_api
from .utils import now_iso

app = FastAPI(title="resume-agent-api", version="0.2.0")


def _serve_page(name: str):
    path = config.PROJECT_ROOT / "frontend" / name
    if path.exists():
        return HTMLResponse(content=path.read_text(encoding="utf-8"))
    return JSONResponse(status_code=404, content={"detail": f"{name} not found"})


@app.get("/")
def root():
    """根路径：产品 Landing 展示页。"""
    return _serve_page("index.html")


@app.get("/studio")
def studio():
    """工作台：简历编辑器。"""
    return _serve_page("studio.html")


@app.get("/ai-create")
def ai_create():
    """AI 对话一键生成简历页。"""
    return _serve_page("ai-create.html")


@app.get("/interview")
def interview():
    """AI 模拟面试页。"""
    return _serve_page("interview.html")


@app.get("/jobs")
def jobs_page(
    request: Request,
    keyword: str = "",
    city: str = "",
    category: str = "",
    sort: str = "",
    limit: Optional[int] = None,
):
    """岗位雷达：浏览器访问返回页面，其余（Accept 非 html）返回岗位 JSON 列表。"""
    if "text/html" in request.headers.get("accept", ""):
        return _serve_page("jobs.html")
    return list_jobs_api(keyword=keyword, city=city, category=category, sort=sort, limit=limit)


@app.get("/health")
def health():
    return {"service": "resume-agent-api", "status": "ok", "date": now_iso()}


SAMPLE_RESUME: dict[str, Any] = {
    "basics": {
        "name": "张三",
        "email": "zhangsan@example.com",
        "phone": "13800000000",
        "location": "上海",
        "summary": "3年前端工程师，熟悉 React/Next.js，负责过中大型 B 端系统。",
    },
    "education": [
        {
            "school": "XX大学",
            "degree": "本科",
            "major": "软件工程",
            "startDate": "2018-09",
            "endDate": "2022-06",
            "highlights": ["GPA 3.8/4.0"],
        }
    ],
    "experience": [
        {
            "company": "某科技公司",
            "role": "前端工程师",
            "startDate": "2022-07",
            "endDate": "至今",
            "highlights": [
                "主导搭建组件库，页面开发效率提升 30%",
                "优化首屏性能，LCP 从 3.2s 降至 1.8s",
            ],
        }
    ],
    "projects": [
        {
            "name": "简历 Agent 平台",
            "description": "支持模板切换、智能一页、PDF 导出与 AI 润色。",
            "highlights": ["完成 MVP 并服务首批内测用户"],
            "link": "https://example.com",
        }
    ],
    "skills": ["TypeScript", "React", "Next.js", "Node.js"],
}


@app.get("/resume/sample")
def sample_resume():
    return SAMPLE_RESUME


# 挂载各业务路由
app.include_router(resumes.router)
app.include_router(ai.router)
app.include_router(jobs.router)

# 挂载前端静态资源（若存在）
FRONTEND_DIR = config.PROJECT_ROOT / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
