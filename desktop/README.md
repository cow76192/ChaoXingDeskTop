# 桌面版使用与开发指南

**版本：0.3.7** · Windows 10 / 11 x64 · Python + PySide6 / QML · GPL-3.0

[项目首页](../README.md) · [下载安装包](https://github.com/mikubob/ChaoXingDeskTop/releases/tag/v0.3.7) · [第三方声明](THIRD_PARTY_NOTICES.md)

本文中的命令默认在 `desktop` 目录的 PowerShell 中执行。

## 安装与升级

安装包包含 Python 环境及运行依赖，默认安装到：

```text
%LOCALAPPDATA%/Programs/ChaoxingDesktop/
```

安装后可通过桌面或开始菜单快捷方式启动。升级前退出旧程序，再安装到原目录；安装器保留原 `installation.json`，沿用已有设置、账号、Cookie 和凭据。卸载保留个人数据。

如果使用完整程序目录，打开 `ChaoxingDesktop.exe` 即可。请保留 `_internal`、`ChaoxingWorker.exe` 及目录中的其他文件；后台组件由主程序启动。

## 使用流程

### 1. 账号与课程

在「课程与账号」登录或导入 Cookie，然后读取课程。可以添加多个账号，为其设置备注，并分别保留加密会话；重启后恢复最后选择的账号。

切换账号会清空当前课程、选择及任务结果，需要重新读取课程。任务运行期间锁定账号切换。导入已绑定账号的 Cookie 时，会校验平台用户身份。

首次体验可以选择「离线演示」，无需连接平台。

### 2. 学习设置与服务

在「学习设置」调整倍速、章节并发、重试和未开放章节处理策略。在「题库与 AI」配置服务顺序、凭据、查询间隔、超时和重试。

声明式 JSON 题库支持 GET / POST、题型映射和响应字段路径，不执行模板中的 JavaScript。真实服务连接测试可能消耗服务额度；图片识别需要模型支持视觉输入。

### 3. 答案处理

题库按顺序查询，AI 补全未解决的题目，人工补全处理剩余答案。随机补全默认关闭，开启后仅处理仍未解决的单选、多选和判断题。

默认只保存答案。自动提交需独立开启，并要求所有题目已有答案；仍有空白题目时仅保存。填空按平台可确认的空位逐一对应，多空答案使用 JSON 字符串数组。

### 4. 进度与任务控制

在「任务与日志」查看章节、媒体与逐题结果。任务进度表示本轮处理进度；媒体达到时长后仍需平台确认，待核验状态不会等同于平台已完成。

「暂停后续」阻止新的调度、答题请求和写入，在途请求及当前媒体可以继续。停止先协作取消，超时后终止后台；已经送达平台的请求不会撤回。

验证码使用本地 CPU OCR。识别不可用或验证类型不支持时，相关章节保留待处理；可在平台页面完成验证后重新登录或导入 Cookie。

## 账号与本机数据

| 内容 | 位置或规则 |
| --- | --- |
| 默认数据目录 | `%LOCALAPPDATA%/ChaoxingDesktop/` |
| 首次安装的独立配置 | 默认数据目录下的 `profiles/installer-<版本>-<标识>/` |
| 设置与账号 | 当前数据目录中的 `settings.ini`、`accounts.json` |
| Cookie | 各账号独立保存，使用 Windows DPAPI 加密 |
| 日志 | 默认位于当前数据目录的 `logs/`，可在界面中修改 |
| 测试与开发隔离 | 通过 `CHAOXING_DESKTOP_DATA` 指定独立目录 |

- Cookie、题库 Token、AI Key、代理和通知凭据使用 Windows DPAPI 加密，通常绑定当前 Windows 用户与本机。登录密码不写入账号文件。
- 旧明文 Cookie 成功迁移并加密保存后删除；迁移失败时保留原文件并提示。
- **完整 INI 导出包含当前明文密码和密钥，应留在本机。** 保存失败或检测到其他进程修改时保留原文件，不覆盖更新状态。
- 日志先脱敏再显示与写盘，单文件约 10 MiB、总量约 100 MiB、保留 14 天。删除仅处理本应用命名的普通日志。
- 同一数据目录仅运行一个主窗口，重复启动会唤起已有窗口。界面日志、逐题结果及后台队列有容量限制。

## 源码运行

开发与构建环境为 **Windows x64、Python 3.13.9**。准备运行环境：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe run.py
```

`run.py` 是主程序入口，后台进程使用同一入口的 `--worker` 模式。界面使用 Qt Quick / QML，以及 FluentWinUI3 和 Fusion / Basic 回退样式。

## 测试

测试和发行构建使用独立 `.venv-build` 环境。先安装锁定的运行与构建依赖：

```powershell
python -m venv .venv-build
.venv-build/Scripts/python.exe -m pip install --no-deps -r requirements-lock.txt
.venv-build/Scripts/python.exe scripts/verify_dependencies.py
.venv-build/Scripts/python.exe -m pip check
```

运行单元与界面回归：

```powershell
.venv-build/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py'
.venv-build/Scripts/python.exe tests/qml_ui_smoke.py
.venv-build/Scripts/python.exe tests/accounts_ui_smoke.py
.venv-build/Scripts/python.exe tests/audit_ui_smoke.py
```

运行离线负载测试：

```powershell
.venv-build/Scripts/python.exe tests/performance_smoke.py --tasks 10000 --events 3000 --questions 1000 --rounds 3 --max-round-seconds 20 --max-heartbeat-p95-ms 500 --output build/performance.json
```

上述测试使用隔离数据与离线模拟。`tests/account_check.py` 是另行执行的手动只读工具，通过隐藏交互输入凭据，不属于离线回归。

## 构建与发布

### 构建程序

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build.ps1 -OutputDirectory dist/release-0.3.8/ChaoxingDesktop
```

构建脚本会准备 `.venv-build`、安装锁定依赖并核对依赖闭包，随后运行单元与源码界面回归、执行 PyInstaller，最后验收冻结 worker 与 QML 界面。

程序输出至 `dist/release-0.3.8/ChaoxingDesktop/`。可通过 `-Wheelhouse <绝对路径>` 使用完整的本地 wheel 目录离线安装。依赖更新需要重新生成、审阅锁文件，并在干净环境中验证。

### 生成安装包

准备 [NSIS 编译器](https://nsis.sourceforge.io/Download)，将下方路径替换为本机的 `makensis.exe`：

```powershell
.venv-build/Scripts/python.exe scripts/build_installer.py --app dist/release-0.3.8/ChaoxingDesktop --compiler "C:/Tools/NSIS/makensis.exe"
```

产物默认写入项目根目录的 `release/`：

```text
ChaoxingDesktop-0.3.8-Setup-win-x64.exe
ChaoxingDesktop-0.3.8-source.zip
ChaoxingDesktop-0.3.8-installer-SHA256.json
```

安装包包含完整程序、对应源码 ZIP、许可和第三方声明，NSIS 编译器不随包分发。生成安装包前会核对程序版本、源码与产物哈希，以及单元、worker、GUI 验收标记；跳过 GUI 的构建不能用于正式发布。修改构建输入后，需要重新构建和验收。

安装器与便携打包共用 `scripts/source_bundle.py` 的公共文件清单，不收集历史计划、截图、验收文档、用户数据或临时文件。升级时只删除 `scripts/retired-runtime-0.3.5.txt` 列出的具体废弃运行文件，不使用通配符或递归删除，也不删除新程序仍包含的文件。

## 0.3.7 音频修复与清理

- 课程列表鼠标滚轮从 160 调整为 136 像素/格，降低 15%；触控板像素滚动和边界限制保持原样。
- 同版本修订将题库与 AI、答案处理、结束通知及设置表单接入同一滚动组件，与课程列表保持一致（136 像素/格）。构建与 CI 增加服务页面实际滚轮事件检查。
- 按播放器模块与旧卡片文件名正确识别 MP3 等音频，状态读取与进度上报均使用音频类型；网络错误不再触发无依据的音频切换。
- 文档、阅读和媒体状态需通过响应校验；每张任务卡保留自己的参数，JSON 解析保留原始空格，未知任务不再静默丢弃。
- 移除桌面路由不再使用的旧选项模糊匹配、答案分段代码及模块，删除无用导入并让测试直接替换实际等待函数。未新增依赖。

## 0.3.6 修复与清理

- 停止、正常完成或章节失败后，可继续使用同一账号的有效会话启动其他课程；后台确认的 Cookie 文件版本会同步到课程身份记录。
- 下拉框统一显示清晰的选中状态，课程列表滚轮步幅增大，课程选择与 ID 按钮具有边框、颜色和切换状态。
- 删除无调用方的通知 INI 读取路径、题库配置文件参数、无用成员和隐藏控件，精简未使用图标；保留旧配置迁移、通知服务及平台兼容逻辑。

## 0.3.5 性能与体积优化

- 逐题结果每条记录只刷新一次脱敏器，模型直接复制经过校验的数据结构，避免重复 JSON 解析；保留嵌套脱敏、快照隔离与容量限制。
- 仅保留默认使用的 `common_old.onnx`，移除未使用的 beta / 检测模型及 OpenCV 视频 I/O 插件。
- 按 QML 导入范围及原生 DLL 依赖闭包收集 Qt，保留 FluentWinUI3、Fusion / Basic、Shapes / Effects、SVG、TLS 和软件 OpenGL。
- 平台适配源码进入 Python 归档，不再重复复制 `.py`；完整源码仍随安装包提供。

体积、离线负载对比和该版本验收结果见 [项目首页](../README.md#035-更新)。

## 讨论任务（0.3.8 新增）

在「题库与 AI → 讨论任务」启用处理，选择回复水平，并独立设置讨论自动提交。新旧配置缺省均为关闭；测验提交开关不影响讨论。运行时设置锁定，变更用于下一轮。

- 精简、中等、详细分别以 50–100、150–250、350–600 字为生成目标，复用现有 AI 地址、Key、模型、间隔和请求预算；正文上限 1000 个 Unicode 字符，超限不会截断后发布。
- 固定模式始终输出单字 `好`，不初始化或请求模型，不补字、不因失败换档；不保证任意课程都接受或得分。
- 预览仅使用输入的示例主题，前三档会请求已配置 AI 服务；固定模式完全本地。预览不读取课程、不发布。
- 关闭自动提交时保存本地草稿；在「任务与日志 → 讨论记录」搜索、按状态筛选、查看与复制正文。查看详情不会触发发布。
- 发布前查本人顶层回复并保存发布意图；独立无重试 transport 发送一次，再读回确认。跨章节、跨轮重试和重启共享话题记录，不能靠删除草稿解除发布去重。
- `discussions/` 位于既有应用数据 / 安装配置目录，按账号、课程、班级、原生空间和话题隔离。备份时应一并保留，尤其是未决发布意图。记录损坏时保留原文件并阻止新发布。

当前支持标准主站章节入口到 groupweb v3 的网页合同；旧版、镜像域和无法确认身份的结构保留待处理。图片或附件题意尚未适配时，普通档位保留待处理。字数 / 业务拒绝如实记录；审核中、响应丢失或读回未定保留发布未知，不重复试发。平台明确拒绝的记录保留待处理，当前不自动清除拒绝记录后重试。

2026-10-19 对用户选定的三个真实话题完成发布、正文读回、任务及章节确认、再次运行去重验收；使用预先审阅的正文核验协议，未调用外部 AI 服务。离线测试覆盖四档生成、异常恢复和隔离行为；不把这一条成功样例推广为所有课程 / 页面都已适配。

## 来源与许可

平台适配参考 [Samueli924/chaoxing](https://github.com/Samueli924/chaoxing)，固定基线为 `45d2106b16764231c2de2038fb042e71b23d878f`。运行不依赖本地参考仓库。

完整来源、依赖和改动说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)，许可文本见 [LICENSE](LICENSE)。
