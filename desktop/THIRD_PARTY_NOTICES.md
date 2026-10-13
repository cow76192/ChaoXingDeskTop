# 来源与许可

桌面版：ChaoxingDesktop 0.2.2，GPL-3.0。完整许可见 LICENSE。

参考与复用来源：https://github.com/Samueli924/chaoxing
固定提交：45d2106b16764231c2de2038fb042e71b23d878f
上游版本元数据：3.1.3

`vendor/chaoxing` 的平台协议适配模块与字体资源来源于上述提交，保留原文件作者与许可。0.2.0 删除旧 main.py、配置模板和终端任务辅助模块；api/answer.py 仅保留改编的题库协议适配器，移除旧 AI、手动输入、回退与标题缓存实现。api/base.py 移除终端进度与随机作答，改为未解决题目留空、全部解决才允许自动提交，并去除重做后的强制提交。api/logger.py 由桌面 worker 接管脱敏日志；api/cxsecret_font.py 使用模块位置加载资源。题库请求恢复 TLS 证书验证，登录、题库与通知请求具有明确超时。

桌面配置默认值、配置迁移、任务调度、答题路由、AI 请求、图片消息和 Qt 交互独立实现于 chaoxing_desktop，运行不加载参考仓库或旧 CLI。其余平台协议实现仍属于来源明确的改编代码，并非完全从零重写。

0.2.1 增加由用户显式启用的随机补全选项，仅作为题库、AI 和人工补全之后的最后回退。随机答案有独立来源标记、不计入服务命中率，并遵循单独的保存 / 自动提交设置；保留未填写题目仅保存的规则。

0.2.2 修复 api/base.py 的会话单例初始化，并直接使用桌面路由核验后的选项编号生成答题表单；api/decode.py 保留选项图片，供视觉模型和人工补全使用。桌面配置统一布尔值大小写，日志逐个过滤各题库 Token。

桌面代码与上游核心一起以 GPL-3.0 提供，源码目录为 desktop；同次交付的源码包包含此目录的源码、构建文件、上游核心与许可，不含用户账号、Cookie 或 API Key。

第三方运行依赖及各自许可保留于打包依赖的 dist-info 和模块文件中。Qt/PySide6 使用其开源许可；依赖版本详见 requirements-lock.txt。本发行包由开源源码构建，未进行代码签名。

PySide6_Essentials 6.12.0 的本地 METADATA 声明许可选择为 `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`。本工程采用 GPL-3.0 开源交付；GPL-3.0 文本随 LICENSE 提供。Qt for Python 源码与构建资料来源：https://code.qt.io/cgit/pyside/pyside-setup.git/ ，文档：https://doc.qt.io/qtforpython 。依赖 DLL 单独放置于 `_internal`，可与匹配版本的自行构建依赖一起使用。
