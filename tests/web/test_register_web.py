import time
import pytest
from pages.base_page import BasePage


@pytest.mark.web
@pytest.mark.write
@pytest.mark.title("页面测试：注册新用户并跳转登录")
def test_register_via_page(page, settings):
    # 1. 动态生成唯一用户名
    unique_id = str(int(time.time()))
    new_username = f"webuser_{unique_id}"
    password = "123456"

    # 2. 初始化并打开页面
    base_page = BasePage(page, settings)
    base_page.open("/register")

    # =====================================================
    # 3. 修改这里：放弃 base_page.fill，直接用 page 原生定位
    # get_by_placeholder 专门用来找输入框里的浅色提示文字
    # =====================================================
    page.get_by_placeholder("请输入用户名").fill(new_username)
    page.get_by_placeholder("请输入密码").fill(password)
    page.get_by_placeholder("请确认密码").fill(password)

    # 点击按钮同样可以用原生方法，按文字匹配（如果是 button 标签用 get_by_role 更准）
    page.get_by_role("button", name="注册").click()
    # 或者用 page.get_by_text("注册").click()

    # 4. 断言成功跳转
    base_page.assert_text("前往登录")

    print(f"\n[页面测试] 成功注册用户: {new_username}")