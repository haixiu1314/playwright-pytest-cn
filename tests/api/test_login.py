import os
import pytest
from framework.assertions import assert_status, assert_json_value, assert_json_type


@pytest.mark.api
@pytest.mark.readonly
@pytest.mark.title("正确账号密码登录成功并返回令牌")
def test_login_success(api_client):
    username = os.environ["AUTOMATION_USERNAME"]
    password = os.environ["AUTOMATION_PASSWORD"]

    response = api_client.post(
        "/api/user/login",
        json={"username": username, "password": password},
    )

    # 1. 打印现在的账号和密码（确认真读取了你改的 .env）
    print(f"\n[当前测试账号] {username} / {password}")

    # 2. 打印真实的响应状态和内容
    print(f"[HTTP状态码] {response.status}")
    print(f"[响应正文] {response.text()}\n")

    # 3. HTTP 状态断言
    assert_status(response, 200)

    # 4. 加严格断言：如果你的业务成功时 code 是 200，必须断言它！
    # 如果你之前打印的 JSON 没有 code，那就换成 msg == "登录成功" 或者对 token 进行断言
    assert_json_value(response, "code", 200)  # ← 换成你成功时的真实业务码