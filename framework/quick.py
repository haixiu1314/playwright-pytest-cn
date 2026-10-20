"""中文交互入口：选择环境、模块和测试类型后启动独立执行进程。"""
import subprocess
import sys
import yaml
from framework.settings import ROOT, load_settings
from framework.declarative import load_specs
from framework.modules import inventory


def choose(prompt, values, default):
    print(prompt)
    for index, value in enumerate(values, 1):
        print(f"  {index}. {value}")
    answer = input(f"输入编号或名称（回车 {default}）：").strip() or default
    if answer.isdigit() and 1 <= int(answer) <= len(values):
        return values[int(answer) - 1]
    if answer not in values:
        raise ValueError("选择不在列表内")
    return answer


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        data = yaml.safe_load((ROOT / "config/environments.yaml").read_text(encoding="utf-8-sig"))
        environment = choose("选择目标环境", list(data["environments"]), data.get("default_environment", "local"))
        settings = load_settings(environment)
        modules = inventory(load_specs(ROOT / "cases"), ROOT / "tests")
        print("可选模块：")
        names = list(modules)
        for index, name in enumerate(names, 1):
            print(f"  {index}. {name}（{modules[name]['name']}）")
        selected = input("模块编号或标识，多个用逗号分隔（回车全部）：").strip()
        selected_names = []
        for entry in selected.replace("，", ",").split(","):
            entry = entry.strip()
            if not entry:
                continue
            name = names[int(entry) - 1] if entry.isdigit() and 1 <= int(entry) <= len(names) else entry
            if name not in modules:
                raise ValueError(f"模块不存在：{name}")
            selected_names.append(name)
        scope = choose("选择测试范围：api 接口 / web 页面 / workflows 联动 / all 全部", ["all", "api", "web", "workflows"], "all")
        args = [sys.executable, "-m", "framework.cli", "--env", environment, "--scope", scope]
        if selected_names:
            args += ["--module", ",".join(selected_names)]
        if scope != "api" and input("显示浏览器窗口？y/N：").strip().lower() == "y":
            args.append("--headed")
        print("开始测试，完成后将显示中文报告路径。", flush=True)
        return subprocess.call(args, cwd=ROOT)
    except (ValueError, OSError, KeyError, yaml.YAMLError) as exc:
        print(f"无法启动：{exc}")
        return 4
    except (KeyboardInterrupt, EOFError):
        print("已取消。")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
