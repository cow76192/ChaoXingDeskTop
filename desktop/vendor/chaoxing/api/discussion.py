"""Chaoxing insertbbs -> chapter -> native groupweb v3 discussion adapter.

Contracts independently observed on 2026-10-19. No mobile endpoints, JS
execution or copying of other students' replies. Unsupported shapes fail closed.
"""
from dataclasses import dataclass, field
import json
import re
import time
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

from api.responses import PlatformResponseError, checked_page
from chaoxing_desktop.control import checkpoint, control_of
from chaoxing_desktop.http import read_response
from chaoxing_desktop.text import plain_text

HOSTS = {'mooc1.chaoxing.com', 'mooc2-ans.chaoxing.com', 'groupweb.chaoxing.com'}
DETAIL_PATH = re.compile(r'^/course/topic/v3/bbs/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)/replysList$')


def trusted_url(url):
    p = urlsplit(url)
    if p.scheme != 'https' or p.hostname not in HOSTS or p.username or p.password or p.port not in (None, 443):
        raise PlatformResponseError('讨论跳转地址不在受信超星主机范围。')
    return url


def bootstrap_value(text, key):
    """Read JSON literals from window.obj without evaluating JavaScript."""
    start = re.search(r'\bwindow\.obj\s*=\s*\{', text)
    if not start:
        raise PlatformResponseError('未识别到新版讨论初始化数据。')
    match = re.search(r'^\s*' + re.escape(key) + r'\s*:\s*', text[start.end():], re.M)
    if not match:
        raise PlatformResponseError('讨论页缺少必要字段：' + key)
    tail = text[start.end() + match.end():]
    try:
        value, _ = json.JSONDecoder().raw_decode(tail)
        return value
    except ValueError:
        # Only a simple string token is permitted; not arbitrary JS syntax.
        if key == 'urlToken' and (m := re.match(r"'([A-Za-z0-9_.=+/-]{1,2048})'", tail)):
            return m.group(1)
        raise PlatformResponseError('讨论初始化字段不是可识别的 JSON。') from None


@dataclass
class Topic:
    uid: str
    course_id: str
    clazz_id: str
    space_id: str
    topic_id: str
    numeric_id: str
    title: str
    body: str
    detail_url: str
    entry_url: str
    token: str = field(repr=False)
    job_id: str = ''
    minimum: int = 0
    maximum: int = 1000
    has_images: bool = False
    can_publish: bool = False


@dataclass(frozen=True)
class ReplyLookup:
    known: bool
    reply_id: str = ''
    content: str = ''


class BusinessRejected(PlatformResponseError):
    pass


class DiscussionAdapter:
    def __init__(self, client):
        from api.base import SessionManager
        self.client = client
        self.session = SessionManager.get_session()
        self.control = control_of(client)

    def read(self, url, params=None):
        url = trusted_url(url)
        for _ in range(6):
            checkpoint(self)
            response = self.session.get(url, params=params, allow_redirects=False,
                                        headers={'Referer': 'https://mooc1.chaoxing.com/'}, timeout=15)
            params = None
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get('Location', '')
                response.close()
                destination = urljoin(url, location)
                if urlsplit(destination).hostname == 'passport2.chaoxing.com':
                    raise PlatformResponseError('讨论会话已失效，请重新登录。', 'auth_error')
                url = trusted_url(destination)
                continue
            return response
        raise PlatformResponseError('讨论页跳转次数超过上限。')

    def html(self, url, params=None):
        with self.read(url, params) as response:
            # cards performs only common HTTP/login/verification checks; the
            # discussion structure and context are validated below separately.
            text = checked_page(response, 'cards')
            return text, str(response.url)

    def data(self, path, params):
        with self.read('https://groupweb.chaoxing.com' + path, params) as response:
            checked_page(response, 'cards')
            try:
                data = response.json()
            except ValueError:
                raise PlatformResponseError('讨论查询没有返回业务 JSON，未将其当作零回复。') from None
            if not isinstance(data, dict) or type(data.get('status')) is not bool:
                raise PlatformResponseError('讨论查询的业务状态结构无效。')
            if data['status'] is not True:
                raise PlatformResponseError('平台未接受讨论查询：' + plain_text(str(data.get('msg', '')))[:200])
            return data

    def resolve(self, course, job, info):
        uid = str(self.client.get_uid())
        if not uid or not job.get('mid') or not info.get('knowledgeid') or not job.get('jobid'):
            raise PlatformResponseError('讨论入口的账号、模块或任务关联缺失。')
        params = dict(mtopicid=job['mid'], jobid=job['jobid'], isPortal='false',
                      knowledgeid=info['knowledgeid'], ut='s', clazzId=course['clazzId'],
                      enc=job.get('enc', ''), courseid=course['courseId'], isJob='true')
        # Native insertbbs serializes absent top.utEnc as the literal undefined;
        # this exact missing-field path was observed working in the target course.
        params['utenc'] = info.get('utenc') or 'undefined'
        entry_url = 'https://mooc1.chaoxing.com/mooc-ans/bbscircle/chapter?' + urlencode(params)
        text, _ = self.html(entry_url)
        soup = BeautifulSoup(text, 'lxml')
        node = soup.select_one('#topicMainDiv[data]')
        if not node:
            raise PlatformResponseError('未识别到章节关联话题入口，未扫描其他讨论区。')
        detail_url = trusted_url(urljoin(entry_url, node['data']))
        match = DETAIL_PATH.fullmatch(urlsplit(detail_url).path)
        if not match or urlsplit(detail_url).hostname != 'groupweb.chaoxing.com':
            raise PlatformResponseError('当前讨论页面版本尚未适配，保留待处理。')
        query = parse_qs(urlsplit(detail_url).query)
        if query.get('courseId') != [str(course['courseId'])] or query.get('classId') != [str(course['clazzId'])]:
            raise PlatformResponseError('讨论详情入口返回了其他课程或班级。')
        text, final_url = self.html(detail_url)
        if urlsplit(final_url).path != urlsplit(detail_url).path:
            raise PlatformResponseError('讨论详情跳转到其他话题，已停止处理。')
        user, native, context, circle = [bootstrap_value(text, k) for k in ('user', 'topic', 'course', 'circle')]
        if not all(isinstance(x, dict) for x in (user, native, context, circle)):
            raise PlatformResponseError('讨论详情数据结构无效。')
        if str(user.get('puid', '')) != uid:
            raise PlatformResponseError('讨论站点身份与课程账号不一致。', 'auth_error')
        if (str(context.get('courseId')) != str(course['courseId'])
                or str(context.get('classId')) != str(course['clazzId'])
                or str(native.get('chapterId')) != str(info['knowledgeid'])):
            raise PlatformResponseError('讨论课程、班级或章节上下文不一致。')
        if (str(native.get('uuid')) != match[2] or str(native.get('bbsid')) != match[1]
                or str(circle.get('bbsid')) != match[1] or not native.get('id')):
            raise PlatformResponseError('讨论原生话题或空间身份不一致。')
        try:
            quote_info = native.get('quoteInfo', '{}')
            quote_info = json.loads(quote_info) if isinstance(quote_info, str) else quote_info
            if not isinstance(quote_info, dict) or str(quote_info.get('jobId')) != str(job['jobid']):
                raise ValueError
            raw_min = job.get('property', {}).get('replywordnum', '')
            minimum = int(raw_min) if raw_min not in ('', None) else 0
            if minimum < 0:
                raise ValueError
        except (ValueError, TypeError):
            raise PlatformResponseError('讨论任务映射或结构化字数要求无效。') from None
        token = bootstrap_value(text, 'urlToken')
        if not isinstance(token, str) or not 0 < len(token) <= 2048:
            raise PlatformResponseError('讨论发布临时参数缺失。')
        body_html = str(native.get('rtf_content') or native.get('content') or '')
        body_soup = BeautifulSoup(body_html, 'lxml')
        return Topic(uid=uid, course_id=str(course['courseId']), clazz_id=str(course['clazzId']),
                     space_id=match[1], topic_id=match[2], numeric_id=str(native['id']),
                     title=plain_text(str(native.get('title', ''))), body=plain_text(body_html),
                     detail_url=detail_url, entry_url=entry_url, token=token, job_id=str(job['jobid']),
                     minimum=minimum, has_images=bool(native.get('content_imgs') or native.get('attachment')
                                                   or body_soup.select_one('img, video, audio, iframe')),
                     can_publish=native.get('lock_reply') == 0 and bool(BeautifulSoup(text, 'lxml').select_one('.topicDetail_editContainer textarea')))

    def own_reply(self, topic):
        params = dict(bbsid=topic.space_id, uuid=topic.topic_id, tag='classId'+topic.clazz_id, order=2)
        seen = set()
        started = time.monotonic()
        for pinned in (True, False):
            for _ in range(20 if not pinned else 1):
                if time.monotonic() - started > 60:
                    return ReplyLookup(False)
                data = self.data('/pc/invitation/getTopReplyList' if pinned else '/pc/invitation/getReplyList', params)
                rows = data.get('datas')
                if not isinstance(rows, list) or len(rows) > 1000:
                    raise PlatformResponseError('讨论回复列表结构无效。')
                for row in rows:
                    if (not isinstance(row, dict) or str(row.get('bbsid')) != topic.space_id
                            or str(row.get('topic_id')) != topic.numeric_id
                            or 'createrPuid' not in row or 'parent_id' not in row):
                        raise PlatformResponseError('讨论回复归属或作者字段不完整。')
                    if str(row['createrPuid']) == topic.uid and str(row['parent_id']) == '-1':
                        if not row.get('uuid') or not isinstance(row.get('content'), str):
                            raise PlatformResponseError('本人回复缺少原生标识或正文。')
                        return ReplyLookup(True, str(row['uuid']), row['content'])
                if pinned:
                    break
                poff = data.get('poff')
                if not isinstance(poff, dict) or type(poff.get('lastPage')) is not int or poff['lastPage'] not in (0, 1):
                    return ReplyLookup(False)
                if poff['lastPage'] == 1:
                    return ReplyLookup(True)
                cursor = (str(poff.get('lastValue', '')), str(poff.get('lastAuxValue', '')))
                if cursor in seen or not cursor[0] or not rows:
                    return ReplyLookup(False)
                seen.add(cursor)
                params.update(lastValue=poff['lastValue'])
                if poff.get('lastAuxValue') is not None:
                    params['lastAuxValue'] = poff['lastAuxValue']
        return ReplyLookup(False)

    def publish_once(self, topic, content):
        import uuid
        if not topic.can_publish or not content or not topic.minimum <= len(content) <= min(1000, topic.maximum):
            raise BusinessRejected('讨论已关闭或正文未通过长度校验。', 'business_error')
        # Match native encodeURIComponent followed by jQuery form encoding.
        data = dict(courseId=topic.course_id, classId=topic.clazz_id, replyId='-1', uuid=str(uuid.uuid4()),
                    topic_content=quote(content, safe="-_.!~*'()"), urlToken=topic.token, bbsid=topic.space_id)
        checkpoint(self)
        # A dedicated transport prevents inherited HTTPAdapter retries and
        # automatic redirect replays. Never mutate the shared Session adapter.
        with requests.Session() as transport:
            transport.mount('https://', HTTPAdapter(max_retries=0))
            transport.headers.update({k: v for k, v in self.session.headers.items()
                                      if k.lower() not in ('authorization', 'cookie')})
            transport.headers.update(Referer=topic.detail_url, Origin='https://groupweb.chaoxing.com')
            transport.cookies.update(self.session.cookies)
            transport.control = self.control
            try:
                response = transport.post('https://groupweb.chaoxing.com/pc/invitation/' + topic.topic_id + '/addReplys',
                                          data=data, allow_redirects=False, timeout=(10, 20), stream=True)
                response = read_response(response, transport, time.monotonic()+30, 2*1024*1024)
                checked_page(response, 'cards')
                result = response.json()
                if not isinstance(result, dict) or type(result.get('status')) is not bool:
                    raise PlatformResponseError('讨论提交返回了未知结构。')
                if result['status'] is False:
                    raise BusinessRejected('平台拒绝讨论回复：' + plain_text(str(result.get('msg', '')))[:200], 'business_error')
                # status=true without datas means awaiting moderation, not
                # verified visible publication. The runner still reads back.
                return result
            finally:
                self.session.cookies.update(transport.cookies)

    def task_status(self, topic):
        text, _ = self.html(topic.entry_url)
        field = BeautifulSoup(text, 'lxml').select_one('input#isFinished')
        return 'confirmed' if field and field.get('value') == 'true' else 'pending'
