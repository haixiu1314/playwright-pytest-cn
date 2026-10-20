"""结果模型及中文状态映射，使用字典便于 JSON 序列化。"""
STATUS_LABELS = {"passed": "通过", "failed": "失败", "error": "错误", "skipped": "跳过", "xfailed": "预期失败"}


def new_case(nodeid, title):
    return {"id": nodeid, "title": title, "status": "skipped", "duration_ms": 0, "steps": [], "phase_results": [], "error": "", "attachments": []}


def final_status(phases):
    if any(x["outcome"] == "failed" and x["phase"] != "call" for x in phases):
        return "error"
    if any(x["outcome"] == "failed" for x in phases):
        return "failed"
    if any(x.get("wasxfail") and x["outcome"] == "skipped" for x in phases):
        return "xfailed"
    if any(x["outcome"] == "skipped" for x in phases):
        return "skipped"
    return "passed" if any(x["phase"] == "call" for x in phases) else "skipped"
