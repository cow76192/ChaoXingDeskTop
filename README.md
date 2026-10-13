# 超星 Windows 桌面版工程

Windows 10/11 x64 桌面应用，基于 Python 与 PySide6，当前版本为 0.2.2，采用 GPL-3.0 许可。

本仓库包含桌面版源码、测试、构建脚本和项目文档：

- `desktop/`：桌面版源码及运行所需的改编平台协议适配层。
- `plans/`：开发计划、验收记录和离线演示截图。
- `docs/`：项目检查报告。

## 源码运行

在项目根目录打开 PowerShell：

```powershell
cd desktop
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe run.py
```

详细使用说明、测试与构建步骤见 [desktop/README.md](desktop/README.md)。构建后的主程序位于 `desktop/dist/ChaoxingDesktop/ChaoxingDesktop.exe`，运行时请保留整个软件目录。

## 参考来源与仓库范围

平台协议适配层参考并改编自 [Samueli924/chaoxing](https://github.com/Samueli924/chaoxing)，基线提交为 `45d2106b16764231c2de2038fb042e71b23d878f`。来源与许可见 [desktop/THIRD_PARTY_NOTICES.md](desktop/THIRD_PARTY_NOTICES.md) 和 [desktop/LICENSE](desktop/LICENSE)。

本地 `reference/` 中的旧终端参考项目不上传，桌面版运行不依赖该目录。虚拟环境、构建产物、`release/` 压缩包和本机配置也已通过 `.gitignore` 排除。历史验收文档提到的这些路径属于本地开发与构建记录。
