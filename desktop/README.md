# 超星 Windows 桌面版

**0.3.5** · Windows 10/11 x64 · Python + PySide6 / QML · GPL-3.0。

入口是 `run.py`，Qt Quick 控件使用 FluentWinUI3 和 Fusion / Basic 回退样式。历史 Widgets 界面已移除。

## 安装与运行

安装包默认安装到 `%LOCALAPPDATA%/Programs/ChaoxingDesktop/`，提供桌面 / 开始菜单快捷方式与卸载入口。更新前退出旧程序，安装到原目录即可沿用已有设置、Cookie 和凭据；安装器保留原 `installation.json`。首次安装使用 `%LOCALAPPDATA%/ChaoxingDesktop/profiles/installer-<版本>-<标识>/`，卸载保留个人数据。

便携程序打开 `ChaoxingDesktop.exe`，并保留完整目录，尤其是 `_internal` 和 `ChaoxingWorker.exe`。后台组件由主程序启动。

源码运行，在本目录执行：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe run.py
```

## 使用

1. 在「课程与账号」登录或导入 Cookie，读取并选择课程；首次体验可运行「离线演示」。添加账号可保留多个会话，切换账号后需重新读取课程。任务期间锁定账号切换。
2. 在「学习设置」调整倍速、并发、章节策略和重做选项。在「题库与 AI」配置服务及查询顺序、凭据、间隔、超时和重试。
3. 开始所选课程，在「任务与日志」查看章节、媒体和逐题结果。「暂停后续」阻止新调度与答题请求；在途请求及当前媒体可继续。停止先协作取消，超时后终止后台。
4. 题库依次查询，AI 补全未解决题目，人工补全用于剩余答案。随机补全默认关闭，开启后仅处理未解决的单选、多选和判断题。

默认只保存答案；自动提交需独立开启，且所有题目已有答案。填空按平台可确认的空位逐一对应，多空答案使用 JSON 字符串数组。任务进度不代表学分或平台最终完成；媒体达到时长后仍需平台确认。

声明式 JSON 题库支持 GET/POST、题型映射和响应点路径，不执行导入的 JavaScript。真实服务连接测试可能消耗额度；AI 图片识别需要模型支持视觉输入。

## 账号与本机数据

- 账号列表支持添加、选择、备注和删除，重启后恢复最后选中的账号。每个账号的 Cookie 独立加密保存。导入已绑定账号的 Cookie 时校验平台用户。
- 设置、账号及默认日志位于 `%LOCALAPPDATA%/ChaoxingDesktop/` 或安装标识选定的 profile。开发测试可通过 `CHAOXING_DESKTOP_DATA` 隔离目录。
- Cookie、题库 Token、AI Key、代理和通知凭据使用 Windows DPAPI 加密，通常绑定当前 Windows 用户与本机。登录密码不写入账号文件。旧明文 Cookie 成功迁移后删除。
- 完整 INI 导出包含当前明文密码和密钥，应留在本机。保存失败或检测到其他进程修改时保留原文件，不覆盖更新状态。
- 界面日志和逐题结果有容量限制，日志先脱敏再显示与写盘。单日志文件约 10 MiB、总量约 100 MiB、保留 14 天；删除仅处理本应用命名的普通日志。
- 同一数据目录仅运行一个主窗口。重复启动会唤起已有窗口。

验证码使用本地 CPU OCR。识别不可用或验证类型不支持时，相关章节保留待处理；可在平台页面完成验证后重新登录或导入 Cookie。

## 测试

开发与构建使用 Windows x64、Python 3.13.9。构建环境安装 `requirements-lock.txt`，包括运行和测试 / 构建依赖。

```powershell
.venv-build/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py'
.venv-build/Scripts/python.exe tests/qml_ui_smoke.py
.venv-build/Scripts/python.exe tests/accounts_ui_smoke.py
.venv-build/Scripts/python.exe tests/audit_ui_smoke.py
.venv-build/Scripts/python.exe tests/performance_smoke.py --tasks 10000 --events 3000 --questions 1000 --rounds 3 --max-round-seconds 20 --max-heartbeat-p95-ms 500 --output build/performance.json
```

这些测试使用隔离数据和离线模拟。`tests/account_check.py` 是另行执行的手动只读工具，通过隐藏交互输入凭据，不属于离线回归。

## 构建与发布

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build.ps1 -OutputDirectory dist/optimized-0.3.5/ChaoxingDesktop
.venv-build/Scripts/python.exe scripts/build_installer.py --app dist/optimized-0.3.5/ChaoxingDesktop --compiler <makensis.exe的绝对路径>
```

构建脚本使用独立 `.venv-build` 环境安装锁定依赖、核对依赖闭包、执行单元和源码界面回归、运行 PyInstaller，并验收冻结 worker 与 QML 界面。可通过 `-Wheelhouse <绝对路径>` 离线安装。依赖更新需重新生成并审阅锁文件。

安装器使用 [NSIS](https://nsis.sourceforge.io/Download)，编译器不随程序分发。安装包含完整程序、许可、第三方声明与对应源码 ZIP。生成安装包前核对程序版本、源码 / 产物哈希和单元、worker、GUI 验收标记；跳过 GUI 的构建不能用于正式发布。

安装器和便携打包统一使用 `scripts/source_bundle.py` 的公共文件清单。源码包只包含运行、测试、构建所需源码、资源、说明与许可，不收集历史计划、截图、验收文档、用户数据或临时文件。

升级时只删除 `scripts/retired-runtime-0.3.5.txt` 列出的具体废弃运行文件，不使用通配符或递归删除，也不删除新程序仍包含的文件。

## 0.3.5 优化

逐题结果每条记录只刷新一次脱敏器；模型直接复制经过校验的数据结构，避免重复 JSON 解析，仍保留嵌套脱敏、快照隔离和容量限制。

发行包仅保留默认使用的 `common_old.onnx`，移除未使用的 beta / 检测模型和 OpenCV 视频 I/O 插件。Qt 按界面导入范围及原生 DLL 依赖闭包收集，保留 FluentWinUI3、Fusion / Basic、Shapes / Effects、SVG、TLS 和软件 OpenGL。平台适配源码已进入 Python 归档，不再重复复制 `.py`；完整源码仍随安装包提供。

## 来源与许可

平台适配参考 [Samueli924/chaoxing](https://github.com/Samueli924/chaoxing)，固定提交 `45d2106b16764231c2de2038fb042e71b23d878f`。运行不依赖本地参考仓库。完整来源、依赖和改动说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 [LICENSE](LICENSE)。
