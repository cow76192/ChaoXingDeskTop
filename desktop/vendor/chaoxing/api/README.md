## 模块说明

- `__init__.py`: 平台协议适配包
- `base.py`: 提供核心功能，包含主要的Chaoxing类和学习功能
- `answer.py`: 仅提供 GO、言溪、LIKE、Adapter 的协议适配；桌面答题策略与 AI 位于 chaoxing_desktop/answers.py
- `cipher.py`: AES加密解密功能
- `config.py`: 全局配置常量
- `cookies.py`: Cookie管理
- `cxsecret_font.py`: 超星字体解析与字体映射表完整性校验
- `decode.py`: 解析超星页面数据
- `exceptions.py`: 自定义异常类
- `font_decoder.py`: 字体解码器
- `logger.py`: 日志入口，脱敏输出由桌面 worker 接管
- `notification.py`: 通知功能
- `captcha.py`: 验证码识别与登录会话恢复模块（CPU OCR）
- `live.py`: 直播任务处理
- `live_process.py`: 直播任务处理逻辑
