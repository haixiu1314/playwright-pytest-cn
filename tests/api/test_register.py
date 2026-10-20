import time
import pytest
from framework.assertions import assert_status, assert_json_value


@pytest.mark.api
@pytest.mark.write
@pytest.mark.title("注册时使用极短密码（测试系统是否未做校验）")
def test_register_weak_password(api_client):
    unique_id = str(int(time.time()))
    new_username = f"weak_{unique_id}"

    # 故意用 1 位数的密码
    new_password = "1"

    payload = {
        "username": new_username,
        "password": new_password
    }

    response = api_client.post("/api/user/register", json=payload)

    assert_status(response, 200)

    # 注意：如果系统的确没做限制，返回 200，说明这行断言能通过（证明系统存在弱密码风险）
    # 如果你希望系统报错拦截，那就应该断言它返回 400 或 500
    assert_json_value(response, "code", 200)