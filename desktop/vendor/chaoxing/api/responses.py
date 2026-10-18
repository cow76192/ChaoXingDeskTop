"""Validate HTTP and page identity before interpreting an empty platform list."""
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup


class PlatformResponseError(RuntimeError):
    def __init__(self, message, kind='protocol_error'):
        super().__init__(message)
        self.kind = kind


def checked_page(response, page, course_id=None, clazz_id=None):
    status = response.status_code
    if status in (401, 403):
        raise PlatformResponseError('平台会话已失效或没有访问权限，请重新登录。', 'auth_error')
    if status == 429:
        raise PlatformResponseError('平台请求限流，请稍后重试。', 'rate_limited')
    if status != 200:
        raise PlatformResponseError(f'平台暂时不可用（HTTP {status}），请稍后重试。', 'service_error')
    text = response.text
    if len(text) > 8 * 1024 * 1024:
        raise PlatformResponseError('平台响应过大，已停止解析。')
    url = str(getattr(response, 'url', '') or '')
    address = urlsplit(url)
    soup = BeautifulSoup(text, 'lxml')
    if (address.hostname == 'passport2.chaoxing.com' and 'login' in address.path.lower()
            or soup.select_one('form input[type="password"]')
            or re.search(r'(?:location(?:\.href)?\s*=|location\.replace\()\s*["\']https?://passport2\.chaoxing\.com', text)):
        raise PlatformResponseError('平台会话已失效，请重新登录。', 'auth_error')
    if ('processverify' in address.path.lower()
            or soup.select_one('form[action*="processVerify"], img[src*="processVerify"], #processVerify')):
        raise PlatformResponseError('平台要求人工验证，请完成验证后重新登录。', 'verification_required')
    if page == 'cards':
        return text  # Optional card slots may be empty, but never HTTP/auth errors.
    if page == 'courses':
        valid = bool(soup.select_one('div.course'))
        empty = soup.select_one('.course-list, .courseList, #courseList, .nullCourse, .course-empty, .no-data, .not-data, .empty')
        valid = valid or bool(empty and re.search(r'暂无课程|没有课程|还没有课程|暂无数据', empty.get_text()))
    elif page == 'folders':
        valid = bool(soup.select_one('ul.file-list')) or bool(re.search(r'courseFolderId|/visit/courselistdata', text))
    else:
        valid = bool(soup.select_one('div.chapter_unit'))
        empty = soup.select_one('#coursetree, .chapter-list, #chapterList, .no-data, .not-data, .empty')
        valid = valid or bool(empty and re.search(r'暂无章节|没有章节|暂无数据|尚未.*章节', empty.get_text()))
        for names, expected in ((('courseid', 'courseId'), course_id), (('clazzid', 'clazzId'), clazz_id)):
            for name in names:
                field = soup.find('input', attrs={'name': name}) or soup.find('input', id=name)
                if field and expected is not None and str(field.get('value', '')) != str(expected):
                    raise PlatformResponseError('平台返回了其他课程的页面，请重新读取课程。')
    if not valid:
        raise PlatformResponseError('无法识别平台页面，可能是验证、维护或页面结构变化；未将其当作空数据。')
    return text
