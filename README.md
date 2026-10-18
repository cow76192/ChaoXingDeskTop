# 超星 Windows 桌面版

Python、PySide6 / QML 桌面应用，支持 Windows 10/11 x64。当前版本 **0.3.5**，采用 [GPL-3.0](LICENSE) 许可。

下载 [0.3.5 安装包](https://github.com/mikubob/ChaoXingDeskTop/releases/tag/v0.3.5)。本版安装包约 90 MiB，相比 0.3.4 减少约 50%；对应源码与 SHA256 清单随发行版提供。

支持多账号及加密 Cookie、课程选择、章节调度、视频 / 音频进度、逐题结果、题库与 AI、人工补全、暂停后续任务、日志和本机设置。首次使用可通过「离线演示」体验。

## 源码运行

在 `desktop` 目录执行：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe run.py
```

开发和构建使用 Windows x64、Python 3.13.9。使用方法、配置及完整构建步骤见 [桌面版说明](desktop/README.md)。

## 项目结构

- `desktop/chaoxing_desktop/`：界面、账号、配置、调度和答题处理。
- `desktop/vendor/chaoxing/`：改编的平台协议及必要字体资源。
- `desktop/tests/`：单元、界面和安装验收。
- `desktop/scripts/`：依赖锁定、构建和发布工具。
- `.github/workflows/`：Windows 离线回归检查。

公共仓库与源码包使用相同的明确文件清单，仅包含运行、测试、构建所需源码、资源、说明及许可。历史计划、截图、验收材料、用户数据及本地构建文件不进入发布内容。

## 0.3.5

- 完整程序目录从约 508.5 MiB 降到 347.8 MiB，减少约 31.6%。
- 删除未使用的 OCR 模型、OpenCV 视频组件和 Qt 模块，保留默认 CPU OCR、界面回退、SVG、TLS 及软件渲染。
- 减少逐题结果的重复脱敏检查和 JSON 解析；相同离线负载每轮平均从约 2.38 秒降到 1.89 秒。此数据不代表真实课程或网络请求提速。
- 清理无调用方的姓名查询、旧计数和题库元数据；覆盖升级清理明确列出的废弃运行文件。

## 数据与许可

账号、Cookie、凭据、设置及日志保存在当前 Windows 用户的本地数据目录中。安装更新保留配置标识；卸载保留个人数据。完整 INI 导出可能包含明文凭据，应留在本机。

平台协议参考并改编自 [Samueli924/chaoxing](https://github.com/Samueli924/chaoxing)，固定提交 `45d2106b16764231c2de2038fb042e71b23d878f`。来源、改动和依赖许可见 [THIRD_PARTY_NOTICES.md](desktop/THIRD_PARTY_NOTICES.md)。
