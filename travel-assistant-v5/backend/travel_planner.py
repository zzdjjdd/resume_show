"""旅游计划生成器：使用 LLM 生成结构化的 markdown 行程"""
from typing import Dict, Any, List
from .llm_client import LLMClient


SYSTEM_PROMPT_TRAVEL = """你是「AI智行助手」的旅游规划专家，专门为用户制定高品质、细致的出行行程。

【你的输出规则】
1. **必须使用中文**输出，所有日期、时间、地点用中文描述。
2. **必须输出 Markdown 格式**，使用以下固定结构（用户偏好多选用复选框风格的 ✅ 标识）：
```
# 🌟 【城市/区域】X天Y晚深度行程

## 📋 行程概览
- 出行时间 / 人数 / 出行风格标签
- 主题亮点（2-3条）

## 🗓️ 第1天
### 🚗 上午：...
### 🍱 中午：...
### 🏛️ 下午：...
### 🌃 晚上：...

（每天如此）

## 💡 实用贴士
- 贴士1
- 贴士2

## 💰 预算参考
| 类别 | 人均 | 备注 |
| --- | --- | --- |
| 住宿 | X | ... |
| 餐饮 | X | ... |
| 交通 | X | ... |
| 门票 | X | ... |
| **合计** | **X** |  |
```
3. 体现用户偏好：人文历史/美食体验/自然风光/现代都市/休闲度假/文艺体验，请根据勾选情况重点安排。
4. 每天安排 3-5 个具体的地点/活动，避免空洞。
5. 添加真实的地理/文化背景，**不要瞎编小众地名**。
6. 给出每段路程的距离或通勤方式（步行/地铁/打车/驾车）。
7. 你可以使用外部地图工具的语义（比如「从A驾车至B约25分钟」），但不要假装已调用实时数据。

【输出风格】
温暖、专业、信息密度高；让用户感受到「私人定制」的精致体验。
"""


def build_travel_messages(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    """根据用户输入构建 LLM 消息"""
    departure = payload.get("departure", "")
    destination = payload.get("destination", "")
    days = payload.get("days", 1)
    people = payload.get("people", 1)
    preferences: List[str] = payload.get("preferences", []) or []
    additional = payload.get("additional", "")

    pref_text = "、".join(preferences) if preferences else "无特殊偏好"

    user_text = f"""请为我制定一次出游行程：

- 出发地：**{departure}**
- 目的地：**{destination}**
- 天数：**{days} 天 {max(0, days - 1)} 晚**
- 人数：**{people} 人**
- 出行偏好（可多选）：**{pref_text}**
- 补充说明：{additional or "无"}

要求：
1. 按照规定的 Markdown 模板输出。
2. 每天包含 3-5 个具体活动/景点/餐厅。
3. 餐饮给出具体餐厅名或菜系建议。
4. 住宿给出区位建议（如「建议住在 XX 区域，靠近地铁/景区」）。
5. 用 emoji 增强可读性，按模板严格输出。
6. 行程时间以 24 小时制呈现。
"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT_TRAVEL},
        {"role": "user", "content": user_text},
    ]


async def generate_travel_plan(llm: LLMClient, payload: Dict[str, Any]) -> Dict[str, Any]:
    """调用 LLM 生成旅游计划，返回 markdown 和原始消息"""
    messages = build_travel_messages(payload)
    resp = await llm.chat(messages, stream=False, temperature=0.8)
    try:
        content = resp["choices"][0]["message"]["content"]
    except Exception as e:
        return {"success": False, "error": f"解析响应失败: {e}", "raw": resp}
    return {
        "success": True,
        "markdown": content.strip(),
        "messages": messages,
    }
