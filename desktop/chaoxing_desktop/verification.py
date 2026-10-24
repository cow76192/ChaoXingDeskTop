"""Allowlisted chapter/personal evidence reads, independent of task runners."""
from datetime import datetime, timezone

from .control import Cancelled, checkpoint


def read_cards(client, channel, course, point):
    """Read cards without get_job_list's empty-page completion side effect."""
    from api.base import SessionManager
    from api.decode import decode_course_card
    from api.responses import checked_page
    session = SessionManager.get_session()
    jobs = []
    for index in range(7):
        checkpoint(channel)
        with session.get('https://mooc1.chaoxing.com/mooc-ans/knowledge/cards',
                         params=dict(clazzid=course['clazzId'], courseid=course['courseId'],
                                     knowledgeid=point['id'], cpi=course['cpi'], ut='s', mooc2=1,
                                     num=str(index), v='2025-0424-1038-3'),
                         timeout=15, allow_redirects=False) as response:
            text = checked_page(response, 'cards')
            import re
            if not re.search(r'\bmArg\s*=', text):
                raise ValueError('任务卡结构未知，未将其当作没有本人记录。')
            rows, info = decode_course_card(text)
        if info.get('notOpen'):
            raise ValueError('章节尚未开放；请在平台确认开放条件。')
        if str(info.get('knowledgeid')) != str(point['id']):
            raise ValueError('任务卡章节身份变化，请重新读取课程。')
        for row in rows:
            if row.get('type') in ('discussion', 'activity'):
                jobs.append((row, dict(info, card_index=str(index))))
        if len(jobs) > 1000:
            raise ValueError('本章节讨论／活动超过核验容量。')
    return jobs


def verify_records(client, channel, course, target, point):
    """Only resolve/own lookup/task status; never instantiate a business runner."""
    import hashlib
    import json
    from api.discussion import DiscussionAdapter
    from api.activity import ActivityAdapter
    for job, info in read_cards(client, channel, course, point):
        checkpoint(channel)
        kind = job['type']
        record_id = hashlib.sha256(json.dumps([target['id'], course['courseId'], course['clazzId'],
                                               job.get('mid', ''), info.get('cardid', job.get('cardid', ''))]).encode()).hexdigest()
        status, task_status = 'unknown', 'pending'
        try:
            if kind == 'discussion':
                adapter = DiscussionAdapter(client)
                context = adapter.resolve(course, job, info)
                checkpoint(channel)
                lookup = adapter.own_reply(context)
                status = 'existing' if lookup.reply_id else 'absent' if lookup.known else 'unknown'
            else:
                adapter = ActivityAdapter(client)
                context = adapter.resolve(course, job, info)
                status = context.participation
            checkpoint(channel)
            task_status = adapter.task_status(context)
            reason = {'existing': '已取得本人参与证据；不证明旧草稿已送达或成绩通过。',
                      'absent': '本次读取未发现本人记录；平台可能延迟，未决意图仍禁止重发。',
                      'unknown': '本人状态证据不足；请在平台检查，不能据此判定未提交。'}[status]
        except Cancelled:
            raise
        except Exception as exc:
            reason = '只读核验失败，保留原记录：' + channel.redactor(str(exc))[:1000]
        checkpoint(channel)
        channel.send('record_verification', id=record_id, task_id=target['id'], kind=kind,
                     participation=status, task_status=task_status,
                     checked_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), reason=reason)


def verify_chapters(client, channel, courses, targets, records=False):
    """Re-read the allowlisted chapter endpoint, never infer submission status."""
    identities = {(str(c['courseId']), str(c['clazzId'])): c for c in courses}
    if not targets or len(targets) > 10000:
        raise ValueError('请选择本轮可定位的章节（最多 10000 项）。')
    if any((str(t['courseId']), str(t['clazzId'])) not in identities for t in targets):
        raise ValueError('课程身份已变化，请重新读取课程。')
    groups = {}
    for target in targets:
        groups.setdefault((str(target['courseId']), str(target['clazzId'])), []).append(target)
    for identity, items in groups.items():
        checkpoint(channel)
        course = identities[identity]
        result = client.get_course_point(course['courseId'], course['clazzId'], course['cpi'])
        if not isinstance(result, dict) or not isinstance(result.get('points'), list):
            raise ValueError('章节核验响应结构未知，保留原状态。')
        points = result['points']
        if any(not isinstance(p, dict) or 'id' not in p for p in points):
            raise ValueError('章节核验响应结构未知，保留原状态。')
        states = {str(p['id']): p.get('has_finished') is True for p in points}
        for target in items:
            checkpoint(channel)
            channel.send('verification', id=target['id'], confirmed=states.get(str(target['pointId']), False),
                         checked_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                         reason='平台已确认章节完成' if states.get(str(target['pointId']), False) else
                                '未取得章节完成证据；不判断答案正确、讨论发布或问卷提交。未决意图保留。')
            if records:
                point = next((p for p in points if str(p['id']) == str(target['pointId'])), None)
                if point is None:
                    channel.send('log', level='WARNING', message='章节已不存在，保留讨论／活动原状态。')
                    continue
                try:
                    verify_records(client, channel, course, target, point)
                except Cancelled:
                    raise
                except Exception as exc:
                    channel.send('log', level='WARNING', message='本人状态未核验：' + str(exc))
    channel.send('verification_done', message='只读核验结束；证据不足或读取失败的事项仍待处理。本人状态、任务点与章节分别判断，未决意图保留，没有调用写入接口。')
