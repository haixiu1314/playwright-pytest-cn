"""中文接口断言：失败时说明预期和实际。"""
import re
from framework.steps import step


def assert_status(response, expected):
    with step(f"验证响应状态码为 {expected}"):
        assert response.status == expected, f"状态码不符合预期：预期 {expected}，实际 {response.status}"


def json_value(response, path):
    try:
        value = response.json()
    except Exception as exc:
        raise AssertionError("接口响应不是有效 JSON") from exc
    if not isinstance(path, str) or not re.fullmatch(r"[A-Za-z_\w-]+(?:\[\d+\])*(?:\.[A-Za-z_\w-]+(?:\[\d+\])*)*", path):
        raise AssertionError(f"字段路径格式无效：{path}")
    try:
        for key, index in re.findall(r"([A-Za-z_\w-]+)|\[(\d+)\]", path):
            value = value[key] if key else value[int(index)]
        return value
    except (KeyError, IndexError, TypeError) as exc:
        raise AssertionError(f"响应中不存在字段路径或类型不匹配：{path}") from exc


def assert_json_value(response, path, expected):
    with step(f"验证响应字段：{path}"):
        actual = json_value(response, path)
        assert actual == expected, f"字段 {path} 不符合预期：预期 {expected!r}，实际 {actual!r}"


def assert_json_type(response, path, expected_type):
    with step(f"验证字段类型：{path}"):
        actual = json_value(response, path)
        assert type(actual) is expected_type, f"字段 {path} 类型不符：预期 {expected_type.__name__}，实际 {type(actual).__name__}"


def assert_duration(api_client, maximum_ms):
    with step(f"验证接口耗时不超过 {maximum_ms} 毫秒"):
        assert api_client.last_duration_ms <= maximum_ms, f"响应超时：阈值 {maximum_ms} 毫秒，实际 {api_client.last_duration_ms} 毫秒"
