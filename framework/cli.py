"""唯一推荐执行入口：确保环境、夹具和中文报告全部启用。"""
import argparse
import sys
import pytest
from framework.settings import ROOT, load_settings
from framework.reporting.plugin import Reporter
from framework import fixtures
from framework.declarative import load_specs, YamlPlugin
from framework.modules import inventory, scaffold


class ChineseParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(4, f"参数错误：{message}\n")


def parser():
    result = ChineseParser(description="Playwright + Pytest 中文自动化测试", add_help=False, usage="%(prog)s [选项]")
    result._optionals.title = "可选参数"
    result.add_argument("-h", "--help", action="help", help="显示帮助")
    result.add_argument("--env", help="目标环境名称，例如 local、staging、production")
    result.add_argument("--scope", choices=["api", "web", "workflows", "all"], default="all", help="测试范围，默认 all")
    result.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    group = result.add_mutually_exclusive_group()
    group.add_argument("--read-only", action="store_true", help="仅执行显式标记 readonly 的用例")
    group.add_argument("--allow-write", action="store_true", help="显式允许线上写入，仍需环境 allow_write=true")
    result.add_argument("--report-dir", help="报告输出根目录，每次运行建立独立子目录")
    result.add_argument("--config", help="自定义 YAML 配置路径")
    result.add_argument("--tests", default="tests", help="用例路径，默认项目 tests 目录")
    result.add_argument("--case-dir", default="cases", help="YAML 模块目录，默认 cases")
    result.add_argument("--module", dest="modules", help="模块标识，多个用逗号分隔；默认全部")
    result.add_argument("--tag", dest="tags", help="标签，多个用逗号分隔，匹配任意一个")
    result.add_argument("--list-modules", action="store_true", help="列出模块，不执行测试")
    result.add_argument("--new-module", help="生成一个未启用的 YAML 模块模板，不执行测试")
    result.add_argument("-k", dest="keyword", help="按 Pytest 用例名称表达式筛选")
    return result


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        options = parser().parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 4
    try:
        settings = load_settings(options.env, options.config)
        options.modules = {x.strip() for x in (options.modules or "").split(",") if x.strip()}
        options.tags = {x.strip() for x in (options.tags or "").split(",") if x.strip()}
        case_dir = settings.root / options.case_dir
        test_path = settings.root / options.tests
        if options.new_module:
            print(f"已生成模块模板：{scaffold(case_dir, options.new_module)}\n填写实际步骤并设置 enabled: true 后执行。", flush=True)
            return 0
        specs = load_specs(case_dir)
        if options.list_modules:
            modules = inventory(specs, test_path)
            for name, detail in modules.items():
                print(f"{name}：{detail['name']}（YAML {detail['yaml']} 条，Python 函数 {detail['python']} 个）")
            if not modules:
                print("暂无模块；使用 --new-module 模块名 生成模板。")
            print("说明：列表包含未启用的 YAML 用例；Python 参数化后的条数以执行收集为准。")
            return 0
        if options.allow_write and not settings.target.get("allow_write", False):
            raise ValueError("目标环境 allow_write=false；请先在环境配置中明确允许写入")
        reporter = Reporter(settings, options)
    except (ValueError, OSError, SyntaxError) as exc:
        print(f"配置错误：{exc}", flush=True)
        return 4
    # 关闭外部插件自动加载，避免用户环境中插件改变语义。
    import os
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    paths = [str(test_path)] if test_path.exists() else []
    if case_dir.exists() and case_dir.resolve() != test_path.resolve():
        paths.append(str(case_dir))
    if not paths:
        print("没有用例目录；使用 --new-module 模块名 创建 YAML 用例。", flush=True)
        return 5
    args = [*paths, "-c", str(ROOT / "pytest.ini"), "-p", "no:terminal", "-p", "no:cacheprovider"]
    if options.keyword:
        args += ["-k", options.keyword]
    try:
        return int(pytest.main(args, plugins=[reporter, fixtures, YamlPlugin(specs)]))
    except Exception as exc:
        print(f"执行异常：{exc}", flush=True)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
