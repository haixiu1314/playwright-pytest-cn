"""页面层基类。具体业务页面继承它。"""
from playwright.sync_api import expect
from framework.steps import step


class BasePage:
    def __init__(self, page, settings):
        self.page = page
        self.settings = settings

    def open(self, path="/"):
        with step("打开目标页面"):
            self.page.goto(self.settings.resolve_url(path, "web"))

    def assert_title(self, expected):
        with step(f"验证页面标题：{expected}"):
            expect(self.page).to_have_title(expected)

    def fill(self, label, value):
        with step(f"填写表单字段：{label}"):
            self.page.get_by_label(label).fill(value)

    def click(self, name):
        with step(f"点击按钮：{name}"):
            self.page.get_by_role("button", name=name, exact=True).click()

    def assert_text(self, text):
        with step(f"验证页面显示文字：{text}"):
            expect(self.page.get_by_text(text, exact=True)).to_be_visible()
