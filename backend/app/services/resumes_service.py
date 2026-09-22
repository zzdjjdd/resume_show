"""简历数据服务：多文件管理、JSON Schema 校验、sharedProfile 同步、持久化。

逻辑参考原 apps/api/src/resumes/resumes.service.ts，保持对外行为一致。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import jsonschema
from jsonschema import Draft202012Validator

from .. import config
from ..utils import new_id, now_iso


class ResumeError(Exception):
    """业务错误基类。"""

    status_code = 400

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class BadRequest(ResumeError):
    status_code = 400


class NotFound(ResumeError):
    status_code = 404


def _load_schema() -> dict:
    path = config.RESUME_SCHEMA_PATH
    if not path.exists():
        raise RuntimeError(
            f"resume schema not found: {path} (expected at {config.RESUME_SCHEMA_PATH})"
        )
    return json.loads(path.read_text(encoding="utf-8"))


RESUME_SCHEMA = _load_schema()
_VALIDATOR = Draft202012Validator(
    RESUME_SCHEMA, format_checker=jsonschema.FormatChecker()
)


def _default_basics() -> dict:
    return {
        "name": "你的姓名",
        "email": "you@example.com",
        "phone": "13800000000",
        "location": "上海",
        "summary": "在这里写你的个人简介，突出方向与成果。",
    }


def _default_resume(
    shared_basics: dict, shared_education: Optional[list] = None
) -> dict:
    resume: dict = {
        "basics": dict(shared_basics),
        "customSections": [
            {
                "title": "工作/实习经历",
                "items": [
                    {
                        "title": "前端工程师",
                        "org": "某科技公司",
                        "period": "2022-07 ~ 至今",
                        "highlights": [
                            "负责核心页面重构",
                            "首屏性能提升 40%",
                            "沉淀组件库规范",
                        ],
                    }
                ],
            },
            {
                "title": "项目经历",
                "items": [
                    {
                        "title": "简历 Agent 平台",
                        "org": "个人项目",
                        "period": "2026",
                        "highlights": ["支持模板切换与 PDF 导出", "支持简历润色与模拟面试"],
                    }
                ],
            },
            {
                "title": "科研/校园经历",
                "items": [
                    {
                        "title": "多模态简历评估研究",
                        "org": "实验室",
                        "period": "2025",
                        "highlights": ["建立简历质量评估指标", "完成 A/B 测试分析"],
                    }
                ],
            },
        ],
        "skills": ["TypeScript", "React", "Next.js"],
    }
    if isinstance(shared_education, list):
        resume["education"] = [dict(x) for x in shared_education]
    return resume


def _normalize_layout(layout: Optional[dict]) -> Optional[dict]:
    if not layout:
        return None
    keys = [
        "pageMarginMm",
        "bodyFontSizePt",
        "lineHeight",
        "headerStyle",
        "accentColor",
        "fontFamily",
        "sectionTitles",
    ]
    out: dict = {}
    for k in keys:
        if k in layout and layout[k] is not None:
            out[k] = layout[k]
    return out or None


def _normalize_config(config: Optional[dict]) -> Optional[dict]:
    if not config:
        return None
    out: dict = {}
    if config.get("templateId"):
        out["templateId"] = config["templateId"]
    layout = _normalize_layout(config.get("layout"))
    if layout:
        out["layout"] = layout
    return out or None


class ResumeService:
    """进程内 Map 存储 + JSON 文件持久化。"""

    def __init__(
        self,
        store_path: Optional[Path] = None,
        seed_example: bool = True,
    ) -> None:
        self._store: dict[str, dict] = {}
        self._store_path = Path(store_path or config.RESUME_FILES_PATH)
        self.shared_basics: dict = _default_basics()
        self.shared_education: Optional[list] = None
        self._hydrate(seed_example)

    # ---- 校验 ----
    def validate(self, input_data: Any) -> dict:
        errors = sorted(
            _VALIDATOR.iter_errors(input_data), key=lambda e: list(e.absolute_path or [])
        )
        if errors:
            msgs = "; ".join(
                f"/{'/'.join(map(str, e.absolute_path)) or ''} {e.message}"
                for e in errors
            )
            raise BadRequest(msgs or "Invalid resume payload")
        return input_data

    def ensure_valid_resume(self, input_data: Any) -> dict:
        return self.validate(input_data)

    # ---- 内部 ----
    def _extract_shared(self, resume: dict) -> dict:
        basics = dict(resume.get("basics") or {})
        edu = (
            [dict(x) for x in resume["education"]]
            if isinstance(resume.get("education"), list)
            else None
        )
        return {"basics": basics, "education": edu}

    def _apply_shared(self, resume: dict) -> dict:
        out = dict(resume)
        out["basics"] = dict(self.shared_basics)
        if isinstance(self.shared_education, list):
            out["education"] = [dict(x) for x in self.shared_education]
        else:
            out.pop("education", None)
        return out

    def _sync_all_with_shared(self) -> None:
        for record in self._store.values():
            record["data"] = self._apply_shared(record["data"])

    def _normalize_default_flags(self) -> None:
        files = list(self._store.values())
        if not files:
            return
        defaults = [f for f in files if f.get("isDefault")]
        if len(defaults) > 1:
            picked = False
            for f in files:
                if f.get("isDefault"):
                    if not picked:
                        picked = True
                    else:
                        f["isDefault"] = False
            return
        if not defaults:
            files[0]["isDefault"] = True

    def _persist(self) -> None:
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 2,
            "files": list(self._store.values()),
            "sharedProfile": {
                "basics": dict(self.shared_basics),
                "education": (
                    [dict(x) for x in self.shared_education]
                    if isinstance(self.shared_education, list)
                    else None
                ),
            },
        }
        self._store_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _hydrate(self, seed_example: bool) -> None:
        restored_shared: Optional[dict] = None

        if self._store_path.exists():
            try:
                raw = json.loads(self._store_path.read_text(encoding="utf-8"))
                files = raw.get("files") or []
                sp = raw.get("sharedProfile") or {}

                resumed: dict = {"basics": sp.get("basics")}
                if isinstance(sp.get("education"), list):
                    resumed["education"] = sp["education"]
                if resumed.get("basics"):
                    shared_resume = self.validate(resumed)
                    restored_shared = self._extract_shared(shared_resume)

                for item in files:
                    try:
                        data = self.validate(item.get("data"))
                    except ResumeError:
                        continue
                    self._store[item["id"]] = {
                        "id": item["id"],
                        "name": item.get("name") or f"简历 {str(item['id'])[-4:]}",
                        "isDefault": bool(item.get("isDefault")),
                        "createdAt": item.get("createdAt") or now_iso(),
                        "updatedAt": item.get("updatedAt") or now_iso(),
                        "data": data,
                        "config": _normalize_config(item.get("config")),
                    }
            except (json.JSONDecodeError, KeyError, TypeError):
                self._store = {}

        if restored_shared is None and self._store:
            first = next(iter(self._store.values()))
            restored_shared = self._extract_shared(first["data"])

        if restored_shared:
            self.shared_basics = restored_shared.get("basics") or self.shared_basics
            self.shared_education = restored_shared.get("education")

        if not self._store:
            now = now_iso()

            if seed_example and config.RESUME_FILES_EXAMPLE_PATH.exists():
                try:
                    example = json.loads(
                        config.RESUME_FILES_EXAMPLE_PATH.read_text(encoding="utf-8")
                    )
                    for item in example.get("files") or []:
                        try:
                            data = self.validate(item.get("data"))
                        except ResumeError:
                            continue
                        self._store[item["id"]] = {
                            "id": item["id"],
                            "name": item.get("name") or f"简历 {str(item['id'])[-4:]}",
                            "isDefault": bool(item.get("isDefault")),
                            "createdAt": item.get("createdAt") or now,
                            "updatedAt": item.get("updatedAt") or now,
                            "data": data,
                            "config": _normalize_config(item.get("config")),
                        }
                    self.shared_basics = dict(
                        (example.get("sharedProfile") or {}).get("basics")
                        or self.shared_basics
                    )
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass

            if not self._store:
                self._store[new_id()] = {
                    "id": new_id(),
                    "name": "默认简历",
                    "isDefault": True,
                    "createdAt": now,
                    "updatedAt": now,
                    "data": _default_resume(self.shared_basics, self.shared_education),
                    "config": None,
                }

        self._sync_all_with_shared()
        self._normalize_default_flags()
        self._persist()

    # ---- 对外 API ----
    def list_files(self) -> list[dict]:
        files = sorted(self._store.values(), key=lambda f: not f["isDefault"])
        files.sort(key=lambda f: 0 if f["isDefault"] else 1)
        return [
            {
                "id": f["id"],
                "name": f["name"],
                "isDefault": f["isDefault"],
                "createdAt": f["createdAt"],
                "updatedAt": f["updatedAt"],
            }
            for f in files
        ]

    def get_file(self, file_id: str) -> dict:
        found = self._store.get(file_id)
        if not found:
            raise NotFound(f"Resume file {file_id} not found")
        return found

    def get_default_file(self) -> dict:
        for f in self._store.values():
            if f.get("isDefault"):
                return f
        raise NotFound("Default resume file not found")

    def create_file(
        self,
        name: str | None = None,
        resume: Any = None,
        file_config: dict | None = None,
    ) -> dict:
        now = now_iso()
        fid = new_id()
        display_name = (name or "").strip() or f"简历 {len(self._store) + 1}"
        if resume is not None:
            incoming = self.validate(resume)
            self.shared_basics = dict(incoming.get("basics") or {})
            self.shared_education = (
                [dict(x) for x in incoming["education"]]
                if isinstance(incoming.get("education"), list)
                else None
            )
            self._sync_all_with_shared()
        else:
            incoming = _default_resume(self.shared_basics, self.shared_education)
        data = self._apply_shared(incoming)
        is_default = len(self._store) == 0
        record = {
            "id": fid,
            "name": display_name,
            "isDefault": is_default,
            "createdAt": now,
            "updatedAt": now,
            "data": data,
            "config": _normalize_config(file_config),
        }
        self._store[fid] = record
        self._normalize_default_flags()
        self._persist()
        return record

    def update_file(
        self, file_id: str, resume: Any, file_config: dict | None = None
    ) -> dict:
        found = self.get_file(file_id)
        data = self.validate(resume)
        self.shared_basics = dict(data.get("basics") or {})
        self.shared_education = (
            [dict(x) for x in data["education"]]
            if isinstance(data.get("education"), list)
            else None
        )
        for f in self._store.values():
            f["data"] = self._apply_shared(f["data"])
        normalized = self._apply_shared(data)
        updated = dict(found)
        updated["data"] = normalized
        if file_config is not None or found.get("config"):
            updated["config"] = _normalize_config(file_config) or found.get("config")
        updated["updatedAt"] = now_iso()
        self._store[file_id] = updated
        self._persist()
        return updated

    def rename_file(self, file_id: str, name: str) -> dict:
        next_name = name.strip()
        if not next_name:
            raise BadRequest("name is required")
        found = self.get_file(file_id)
        updated = dict(found)
        updated["name"] = next_name
        updated["updatedAt"] = now_iso()
        self._store[file_id] = updated
        self._persist()
        return updated

    def set_default_file(self, file_id: str) -> dict:
        target = self.get_file(file_id)
        for f in self._store.values():
            f["isDefault"] = f["id"] == file_id
        target["updatedAt"] = now_iso()
        self._persist()
        return target

    def delete_file(self, file_id: str) -> dict:
        if file_id not in self._store:
            raise NotFound(f"Resume file {file_id} not found")
        removed = self._store.pop(file_id)
        if not self._store:
            now = now_iso()
            nid = new_id()
            self._store[nid] = {
                "id": nid,
                "name": "默认简历",
                "isDefault": True,
                "createdAt": now,
                "updatedAt": now,
                "data": _default_resume(self.shared_basics, self.shared_education),
                "config": None,
            }
        elif removed.get("isDefault"):
            newest = sorted(self._store.values(), key=lambda f: f["updatedAt"])[-1]
            for f in self._store.values():
                f["isDefault"] = f["id"] == newest["id"]
        self._normalize_default_flags()
        self._persist()
        return {
            "deletedId": file_id,
            "nextDefaultId": self.get_default_file()["id"],
        }

    # ---- 兼容旧接口 ----
    def create(self, input_data: Any) -> dict:
        file = self.create_file(resume=input_data)
        return {
            "id": file["id"],
            "createdAt": file["createdAt"],
            "updatedAt": file["updatedAt"],
            "data": file["data"],
        }

    def find_all(self) -> list[dict]:
        return [
            {
                "id": f["id"],
                "createdAt": f["createdAt"],
                "updatedAt": f["updatedAt"],
                "data": f["data"],
            }
            for f in self._store.values()
        ]

    def find_one(self, file_id: str) -> dict:
        file = self.get_file(file_id)
        return {
            "id": file["id"],
            "createdAt": file["createdAt"],
            "updatedAt": file["updatedAt"],
            "data": file["data"],
        }
