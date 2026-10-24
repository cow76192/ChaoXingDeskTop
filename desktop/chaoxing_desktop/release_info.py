"""Offline release information and fixed, user-opened public destinations."""
import platform
import sys
from . import __version__

RELEASE_URLS = dict(latest='https://github.com/mikubob/ChaoXingDeskTop/releases/latest',
                    notes='https://github.com/mikubob/ChaoXingDeskTop/releases')


def verification_info():
    return '\n'.join(['ChaoXingDesktop ' + __version__,
                      '运行方式：' + ('冻结程序' if getattr(sys, 'frozen', False) else '源码开发快照（未发行改动可能尚未包含在版本号中）'),
                      '系统：' + platform.system() + ' ' + platform.release() + ' / ' + platform.machine(),
                      'Python：' + platform.python_version(),
                      '发行来源：' + RELEASE_URLS['notes'],
                      '下载后应与该次发行的 SHA256 清单逐项核对；当前未执行安装包校验。',
                      'SHA256 只证明内容一致，不替代发布者签名。未宣称本构建已签名或为最新版本。'])
