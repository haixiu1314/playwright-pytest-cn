# 中文自动化测试平台

这是一个支持接口、Web 和联动测试的中文 Web 平台。通过页面管理环境、模块和用例，勾选多个模块运行，实时查看日志，生成中文报告与失败证据。内部复用 Playwright + Pytest，既有业务用例与报告保持兼容。

**日常入口：双击 `start-platform.cmd`，打开 http://127.0.0.1:8765 。** 保留启动窗口，按 Ctrl+C 关闭。每套系统配置一次环境，普通接口填写表单，Web 场景组合页面步骤；复杂流程保留高级配置和 Python 扩展。当前为仅本机使用的平台。

先读 [平台操作与学习指南](docs/平台操作与学习指南.md)，查看 [平台需求与接口设计](docs/平台需求与接口设计.md)、[平台开发进度](docs/平台开发进度.md) 和 [验证记录](docs/验证记录.md)。

原有 CLI/quick.cmd 继续兼容，以下为内部执行引擎的高级用法，普通操作使用网页即可：

```powershell
# 先在本目录打开 PowerShell
.\.venv\Scripts\python.exe -m framework.cli --list-modules
.\.venv\Scripts\python.exe -m framework.cli --new-module orders
# 填写 cases/orders.yaml，启用后运行
.\.venv\Scripts\python.exe -m framework.cli --env local --module orders
# 多模块用逗号分隔；也可省略 --module 执行全部
.\.venv\Scripts\python.exe -m framework.cli --env local --module login,register --scope api
```

## 1. 从这里开始

项目目录：`E:\test-projectA\web`。在 PowerShell 中切换至该目录。

```powershell
Set-Location E:\test-projectA\web
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -B -m test_platform.server
```

无需激活虚拟环境，也无需修改系统 Python。当前机器使用 Python 3.12.7 创建 `.venv`。

当前项目已经在上述目录完成依赖安装和集成验收，浏览器配置使用本机 Edge。Chromium 的 E 盘下载尝试未成功完成，具体路径和后续安装方法见 [环境与浏览器](docs/环境与浏览器.md)。

在页面「环境配置」中将 local 的页面、接口地址换成实际服务地址并保存；不使用的类型可留空。也可直接维护 `config/environments.yaml`。示例域名不能作为真实业务目标。

日常顺序：环境配置 → 模块与用例 → 新建模块 → 新增接口或 Web 用例 → 开始测试 → 勾选多模块 → 查看执行详情和中文报告。现有 Python 模块会自动显示，可直接选择执行。

按 [多模块快速测试](docs/多模块快速测试.md) 添加 YAML 用例，或按 [学习指南](docs/学习指南.md) 第 8 节添加 Python 业务用例后运行：

```powershell
.\.venv\Scripts\python.exe -m framework.cli --env local --scope api
.\.venv\Scripts\python.exe -m framework.cli --env local --scope web --headed
.\.venv\Scripts\python.exe -m framework.cli --env staging --scope all
.\.venv\Scripts\python.exe -m framework.cli --env production --read-only
```

也可使用包装脚本：`powershell -ExecutionPolicy Bypass -File .\run.ps1 --env local --scope api`。该参数只作用于本次 PowerShell 进程，不修改系统执行策略。

结束后终端会打印报告的绝对路径。打开 `reports/<运行编号>/report.html`，可以按用例名称和状态筛选；将整个运行目录复制给其他人即可离线查看截图。Trace 需要使用 Playwright 打开：

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\.browsers"
.\.venv\Scripts\python.exe -m playwright show-trace .\reports\实际运行编号\attachments\实际文件名.zip
```

## 2. 重新安装或迁移

```powershell
# 使用本机 Python 创建环境；迁移机器上使用对应 Python 3.11+ 路径。
& 'E:\work\ai\Anaconda\Anaconda\python.exe' -m venv .venv
$env:TEMP = "$PWD\.runtime\tmp"
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-cache-dir --no-build-isolation --no-deps -e .
.\install-browser.ps1
```

`requirements.lock.txt` 是本机验证后冻结的完整依赖版本，用于复现环境；`pyproject.toml` 描述兼容范围。首次开发时创建的 `.venv` 已安装依赖，日常使用不必重复安装。

浏览器默认放在项目 `.browsers` 下，运行脚本和配置加载器会设置 `PLAYWRIGHT_BROWSERS_PATH`。如果迁移后浏览器不存在，运行安装脚本。若无法下载且本机已安装 Edge，将配置 `execution.browser` 改为 `msedge`，无需运行 Playwright 的 Edge 安装命令。

只有选择 Chromium 时才需要项目 `.browsers` 中的下载内容。当前使用 Edge，直接读取系统已安装的浏览器，不会再下载一份。

## 3. 认证与环境

复制 `.env.example` 为 `.env`，按需填写 Token、账号、密码或 Playwright 登录状态文件。框架自动将 Token 用于接口请求；账号和密码由你的登录夹具读取，不会猜测登录表单。页面登录可以在 `tests/conftest.py` 扩展，也可以配置已有 `AUTOMATION_STORAGE_STATE`。

默认允许访问当前类型的配置 origin（协议、域名、端口）。前端需要调用不同 origin 的 API、CDN、登录服务时，将精确地址添加到当前环境 `allowed_origins`。不要把所有环境都放入允许列表。接口禁止自动跟随重定向，需要检查 Location 后显式请求。

线上环境默认只读。用例必须声明 `readonly`，否则跳过。线上写入需要环境配置 `allow_write: true` 且命令包含 `--allow-write`。只读 HTTP 方法也可能在设计不规范的业务系统中产生写入，因此业务标记必须由你根据实际行为填写。

## 4. 交付内容

- `start-platform.cmd`：双击启动平台。
- `test_platform/`：HTTP API、环境/模块管理、异步任务、SQLite 历史和中文页面。
- `framework/`：平台内部执行引擎，负责配置、断言、生命周期与中文报告。
- `cases/`：平台管理的正式模块配置与公共流程。
- `pages/base_page.py`：页面基类；具体业务页面按需继承。
- `tests/`：真实业务用例位置，交付时没有保留开发临时用例。
- `docs/平台操作与学习指南.md`：网页操作、架构、各层与各文件职责。
- `docs/平台需求与接口设计.md`：最新产品基线、API 请求格式与执行状态。
- `docs/学习指南.md`：内部执行引擎的逐文件说明、例子和扩展。
- `docs/平台开发进度.md`：平台各阶段实施与验证记录。
- `docs/验证记录.md`：最终验证结果、限制和清理说明。
- `docs/环境与浏览器.md`：实际解释器、依赖及浏览器安装位置。

推荐通过网页平台使用。需要 CLI 集成时通过 `python -m framework.cli` 执行；裸 `pytest` 不会自动配置平台内部的插件与夹具。不要同时通过 CLI 和平台向同一报告目录并行写入。
