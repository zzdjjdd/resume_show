"""简历数据 Pydantic 模型。

数据形状与原 apps/api/src/resumes/resume.types.ts 保持一致，
以保证兼容现有的 resume-files.json 数据文件。
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ResumeBasics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    email: str
    phone: Optional[str] = None
    location: Optional[str] = None
    summary: Optional[str] = None
    photo: Optional[str] = None
    extraInfos: Optional[list[dict[str, str]]] = None


class ResumeEducation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    school: str
    degree: str
    major: Optional[str] = None
    startDate: str
    endDate: str
    gpa: Optional[str] = None
    schoolTags: Optional[str] = None
    college: Optional[str] = None
    summary: Optional[str] = None
    highlights: Optional[list[str]] = None


class ResumeExperience(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str
    role: str
    startDate: str
    endDate: str
    highlights: Optional[list[str]] = None


class ResumeCustomSectionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    org: Optional[str] = None
    period: Optional[str] = None
    highlights: Optional[list[str]] = None


class ResumeCustomSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    items: list[ResumeCustomSectionItem]


class ResumeModel(BaseModel):
    """宽松模型：先通过 JSON Schema 严格校验，再在此做类型化兜底。"""

    model_config = ConfigDict(extra="allow")

    basics: ResumeBasics
    education: Optional[list[ResumeEducation]] = None
    experience: Optional[list[ResumeExperience]] = None
    projects: Optional[list[dict[str, Any]]] = None
    skills: Optional[list[str]] = None
    customSections: Optional[list[ResumeCustomSection]] = None


class LayoutConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pageMarginMm: Optional[float] = None
    bodyFontSizePt: Optional[float] = None
    lineHeight: Optional[float] = None
    headerStyle: Optional[Literal["default", "centered"]] = None
    accentColor: Optional[str] = None
    fontFamily: Optional[str] = None
    sectionTitles: Optional[dict[str, str]] = None


class ResumeFileConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    templateId: Optional[str] = None
    layout: Optional[LayoutConfig] = None


# ---- 对外 DTO ----

class ResumeFileSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    isDefault: bool
    createdAt: str
    updatedAt: str


class ResumeFileRecord(ResumeFileSummary):
    data: dict[str, Any]
    config: Optional[ResumeFileConfig] = None


class ResumeRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    createdAt: str
    updatedAt: str
    data: dict[str, Any]


class TemplateDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    description: str
    layout: Literal["single-column"] = "single-column"
    tokens: dict[str, Any]
