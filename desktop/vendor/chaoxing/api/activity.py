"""Chapter insertvote -> native web questionnaire v2 adapter.

See ACTIVITY_PROTOCOL.md. No guessed mobile activity endpoints, JS execution,
grade generation, or POST retries. Temporary signatures remain in memory.
"""
from dataclasses import dataclass, field
import json
import time
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

from api.responses import PlatformResponseError, checked_page
from chaoxing_desktop.control import checkpoint, control_of
from chaoxing_desktop.http import read_response
from chaoxing_desktop.text import plain_text

HOSTS = {'mooc1.chaoxing.com', 'mooc2-ans.chaoxing.com', 'mobilelearn.chaoxing.com'}
PAGES = {'/page/questionnaire/answerQuestionChapter', '/page/questionnaire/studentQuestionChapter',
         '/page/questionnaire/quesStatisticsChapter'}


def trusted_url(url):
    p = urlsplit(url)
    if (p.scheme != 'https' or p.hostname not in HOSTS or p.username or p.password
            or p.port not in (None, 443)):
        raise PlatformResponseError('活动跳转地址不在已核实的超星主机范围。')
    return url


@dataclass
class ActivityContext:
    uid: str
    course_id: str
    clazz_id: str
    namespace: str
    activity_id: str
    title: str
    questions: list
    kind: str = 'survey'
    can_submit: bool = False
    participation: str = 'unknown'
    receipt: str = ''
    detail_url: str = field(default='', repr=False)
    form: dict = field(default_factory=dict, repr=False)
    course: dict = field(default_factory=dict, repr=False)
    job: dict = field(default_factory=dict, repr=False)
    info: dict = field(default_factory=dict, repr=False)

    @property
    def identity(self):
        return self.uid, self.course_id, self.clazz_id, self.namespace, self.activity_id


def parse_questions(data):
    """Normalize only fields whose semantics were verified in the web template."""
    rows = data.get('questionlist')
    if (not isinstance(rows, list) or not 0 < len(rows) <= 100
            or type(data.get('questioncount')) is not int or data['questioncount'] != len(rows)):
        raise PlatformResponseError('活动题目尚未完整加载、分页未适配或超过 100 题上限。')
    questions, seen = [], set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise PlatformResponseError('活动题目结构无效。')
        qid = str(raw.get('id') or '')
        kind = {0: 'single', 1: 'multiple', 4: 'text', 6: 'text'}.get(raw.get('type'), 'unsupported')
        if not qid or len(qid) > 256 or qid in seen or type(raw.get('type')) is not int:
            raise PlatformResponseError('题目原生标识或类型无效。')
        seen.add(qid)
        content = raw.get('content')
        if not isinstance(content, str) or not content.strip() or len(content) > 12000:
            raise PlatformResponseError('题干为空或超过输入预算。')
        q = dict(id=qid, type=kind, title=plain_text(content), required=raw.get('ismust') == 1,
                 options=[], minimum=1, maximum=1, min_length=0, max_length=1000, reason='')
        # Unknown conditional/format contracts cannot be inferred from labels.
        if (raw.get('jsonConfig') not in (None, {}) or raw.get('config') not in (None, '', '{}')
                or raw.get('pageNum') not in (None, 0)
                or raw.get('imgs') or raw.get('recs') or raw.get('imgArray') or raw.get('recArray')
                or BeautifulSoup(content, 'lxml').select_one('img,video,audio,iframe')):
            q.update(type='unsupported', reason='图片、附件、分页或条件规则尚未适配。')
        if kind in ('single', 'multiple'):
            try:
                options = json.loads(raw['options']) if isinstance(raw.get('options'), str) else raw['options']
                if not isinstance(options, list) or not 0 < len(options) <= 100:
                    raise ValueError
                option_ids = set()
                for option in options:
                    # name is the native submitted value in this specific web
                    # contract, even when it happens to be A/B. Never use index.
                    if not isinstance(option, dict) or set(option) - {'name', 'content', 'mycheck'}:
                        q.update(type='unsupported', reason='选项含未适配的限制或附加文本。')
                    oid, text = option.get('name'), option.get('content')
                    if (not isinstance(oid, str) or not 0 < len(oid) <= 256 or oid in option_ids
                            or not isinstance(text, str) or not text.strip() or len(text) > 4000):
                        raise ValueError
                    option_ids.add(oid)
                    if BeautifulSoup(text, 'lxml').select_one('img,video,audio,iframe'):
                        q.update(type='unsupported', reason='选项包含尚未适配的媒体。')
                    q['options'].append(dict(id=oid, text=plain_text(text)))
                if kind == 'multiple':
                    limit = raw.get('answerLimitMap')
                    if limit is None:
                        # Native template applies no count constraint without
                        # answerLimitMap; filled multiple choice still has >=1.
                        q.update(minimum=1, maximum=len(options))
                    elif (isinstance(limit, dict) and type(limit.get('min')) is int
                          and type(limit.get('max')) is int
                          and 0 <= limit['min'] <= limit['max'] <= len(options)):
                        q.update(minimum=max(1, limit['min']), maximum=limit['max'])
                    else:
                        raise ValueError
            except (ValueError, TypeError, KeyError, AttributeError):
                raise PlatformResponseError('活动选项标识或选择数量限制无效。') from None
        if q['type'] == 'unsupported' and not q['reason']:
            q['reason'] = '当前题型尚未适配，整份活动不会自动提交。'
        questions.append(q)
    if len(json.dumps(questions, ensure_ascii=False).encode()) > 512 * 1024:
        raise PlatformResponseError('标准化活动超过 512 KiB 上限。')
    return questions


class ActivityAdapter:
    def __init__(self, client):
        from api.base import SessionManager
        self.client, self.session = client, SessionManager.get_session()
        self.control = control_of(client)

    def read(self, url, params=None):
        url = trusted_url(url)
        for _ in range(6):
            checkpoint(self)
            response = self.session.get(url, params=params, allow_redirects=False, timeout=20,
                                        headers={'Referer': 'https://mooc1.chaoxing.com/'})
            params = None
            if response.status_code in (301, 302, 303, 307, 308):
                destination = urljoin(response.url, response.headers.get('Location', ''))
                response.close()
                if urlsplit(destination).hostname == 'passport2.chaoxing.com':
                    raise PlatformResponseError('活动会话失效，请重新登录。', 'auth_error')
                url = trusted_url(destination)
                continue
            try:
                return checked_page(response, 'cards'), trusted_url(response.url)
            finally:
                response.close()
        raise PlatformResponseError('活动入口重定向次数超过上限。')

    def data(self, url, params=None):
        text, _ = self.read(url, params)
        try:
            data = json.loads(text)
            if not isinstance(data, dict) or type(data.get('result')) is not int:
                raise ValueError
        except (ValueError, TypeError):
            raise PlatformResponseError('活动接口没有返回已核实的 JSON 结构。') from None
        if data['result'] != 1 or not isinstance(data.get('data'), dict):
            raise PlatformResponseError('平台拒绝读取活动：' + plain_text(str(data.get('errorMsg') or data.get('msg') or '未知原因'))[:200])
        return data['data']

    def resolve(self, course, job, info):
        if job.get('page_variant') != 'insertvote-v2':
            raise PlatformResponseError('当前活动页面版本尚未适配，保留待处理。')
        uid = str(self.client.get_uid())
        if not all(str(info.get(k) or '') for k in ('knowledgeid', 'ktoken', 'cardid')):
            raise PlatformResponseError('活动章节上下文不完整。')
        native_id = str(job.get('property', {}).get('id') or '')
        if not all((native_id, str(job.get('mid') or ''), str(job.get('jobid') or ''), job.get('enc'))):
            raise PlatformResponseError('活动原生身份或入口参数不完整。')
        params = dict(api=1, workId=native_id, jobid=job['jobid'], needRedirect='true', type='vote',
                      knowledgeid=info['knowledgeid'], ktoken=info['ktoken'], clazzId=course['clazzId'],
                      enc=job['enc'], utenc='', courseid=course['courseId'], isjob='true', ut='s', votetype=1, backBtn=1)
        text, final_url = self.read('https://mooc1.chaoxing.com/mooc-ans/api/work', params)
        parsed, query = urlsplit(final_url), parse_qs(urlsplit(final_url).query)
        if parsed.hostname != 'mobilelearn.chaoxing.com' or parsed.path not in PAGES:
            raise PlatformResponseError('活动详情页面变体尚未适配。')
        for key, expected in (('activeId', native_id), ('courseId', course['courseId']), ('classId', course['clazzId'])):
            if query.get(key) != [str(expected)]:
                raise PlatformResponseError('活动详情返回了其他课程、班级或活动。', 'identity_error')
        soup = BeautifulSoup(text, 'lxml')
        actor = soup.select_one('input[name="puid"]')
        if actor and actor.get('value') != uid:
            raise PlatformResponseError('问卷页面账号与课程账号不一致。', 'auth_error')
        extra = query.get('moreClassAttendEnc', [''])[0]
        data = self.data('https://mobilelearn.chaoxing.com/v2/apis/quiz/quizDetail',
                         dict(activeId=native_id, moreClassAttendEnc=extra))
        active = data.get('pptActive')
        if (str(data.get('puid') or '') != uid or not isinstance(active, dict)
                or str(active.get('id')) != native_id or active.get('activeType') not in (14, 43)
                or type(data.get('fid')) is not int or data['fid'] <= 0
                or query.get('fid', ['0'])[0] not in ('0', str(data.get('fid')))):
            raise PlatformResponseError('活动身份、账号或单位空间无法核实。', 'auth_error')
        # The official page distinguishes null participation from status=3.
        if 'pptUserAttend' not in data:
            participation, receipt = 'unknown', ''
        else:
            attend = data['pptUserAttend']
            participation, receipt = 'unknown', ''
            if attend is None:
                participation = 'absent'
            elif isinstance(attend, dict):
                if (any(k in attend and str(attend[k]) != uid for k in ('puid', 'uid'))
                        or any(k in attend and str(attend[k]) != native_id for k in ('activeId', 'activeid'))):
                    raise PlatformResponseError('活动参与记录归属与当前账号不一致。', 'auth_error')
                if attend.get('status') == 3:
                    participation, receipt = 'existing', str(attend.get('id') or native_id)
                elif attend.get('status') in (0, 1, 2):
                    participation = 'absent'
        questions = parse_questions(data)
        form = dict(courseId=str(course['courseId']), classId=str(course['clazzId']), activeId=native_id,
                    preventsubmit='1')
        return ActivityContext(uid, str(course['courseId']), str(course['clazzId']), 'mobilelearn:'+str(data['fid']),
                               native_id, plain_text(str(active.get('name') or job.get('name') or '章节活动')),
                               questions, 'poll' if active['activeType'] == 43 else 'survey',
                               active.get('status') == 1 and participation == 'absent' and actor is not None
                               and query.get('readOnly', ['0'])[0] == '0', participation, receipt, final_url,
                               form, dict(course), dict(job), dict(info))

    def submit_once(self, context, answers):
        from chaoxing_desktop.activity import validate_answer
        if not context.can_submit or context.participation != 'absent':
            raise PlatformResponseError('活动当前不允许提交。')
        mapped = {a['question_id']: a for a in answers}
        if len(mapped) != len(answers) or set(mapped) != {q['id'] for q in context.questions}:
            raise ValueError('提交答案与整卷题目不对应。')
        fields = list(context.form.items())
        for question in context.questions:
            answer = mapped[question['id']]
            reason = validate_answer(question, answer)
            if reason:
                raise ValueError(reason)
            qid = question['id']
            fields.append(('questionId', qid))
            values = answer.get('option_ids') if question['type'] in ('single', 'multiple') else [answer['text']]
            fields.extend(('answer'+qid, v) for v in values)
        return self._once('post', 'https://mobilelearn.chaoxing.com/v2/apis/studentQuestion/doQuestion',
                          context.detail_url, data=fields)

    def _once(self, method, url, referer, **kwargs):
        checkpoint(self)
        with requests.Session() as transport:
            transport.mount('https://', HTTPAdapter(max_retries=0))
            transport.headers.update({k: v for k, v in self.session.headers.items()
                                      if k.lower() not in ('authorization', 'cookie')})
            transport.headers.update(Referer=referer, Origin='https://'+urlsplit(url).hostname)
            transport.cookies.update(self.session.cookies)
            transport.control = self.control
            try:
                response = transport.request(method, trusted_url(url), allow_redirects=False,
                                             timeout=(10, 20), stream=True, **kwargs)
                response = read_response(response, transport, time.monotonic()+30, 2*1024*1024)
                checked_page(response, 'cards')
                result = response.json()
                if not isinstance(result, dict):
                    raise PlatformResponseError('活动写入返回了未知结构。')
                if method == 'post':
                    if type(result.get('result')) is not int:
                        raise PlatformResponseError('活动提交返回了未知结构。')
                    if result['result'] != 1:
                        raise PlatformResponseError('平台拒绝活动答卷：'+plain_text(str(result.get('errorMsg') or '未知原因'))[:200], 'business_error')
                return result
            finally:
                self.session.cookies.update(transport.cookies)

    def finish_task_once(self, context):
        # Official answerQuestionChapter.js calls the native job callback only
        # after submission succeeds. We additionally require participation proof.
        if context.participation != 'existing' or not context.job.get('jtoken'):
            return
        self._once('get', 'https://mooc1.chaoxing.com/mooc-ans/job/vote', context.detail_url,
                   params=dict(jobid=context.job['jobid'], knowledgeid=context.info['knowledgeid'],
                               courseid=context.course_id, clazzid=context.clazz_id, jtoken=context.job['jtoken'],
                               checkMicroTopic='true', microTopicId=context.job.get('microTopicId') or ''))

    def task_status(self, context):
        from api.decode import decode_course_card
        text, _ = self.read('https://mooc1.chaoxing.com/mooc-ans/knowledge/cards',
                            dict(clazzid=context.clazz_id, courseid=context.course_id,
                                 knowledgeid=context.info['knowledgeid'], num=context.info.get('card_index', '0'),
                                 ut='s', cpi=context.course.get('cpi', ''), mooc2=1))
        jobs, info = decode_course_card(text)
        if str(info.get('knowledgeid')) != str(context.info['knowledgeid']):
            return 'pending'
        matches = [j for j in jobs if j['type'] == 'activity' and j.get('mid') == context.job.get('mid')
                   and j.get('jobid') == context.job.get('jobid')]
        if len(matches) == 1 and matches[0].get('server_finished') is True:
            return 'confirmed'
        return 'pending'
