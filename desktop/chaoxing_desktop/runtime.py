"""Application orchestration, independent of the reference CLI entry point."""
from enum import Enum
import threading

from api.base import Account, Chaoxing, StudyResult
from api.notification import Notification
from .answers import build_answers


class ChapterResult(Enum):
    SUCCESS = 0
    ERROR = 1
    NOT_OPEN = 2


def create_client(config, channel, courses_only=False):
    from api.answer import DummyTiku
    common = config["common"]
    answers = DummyTiku() if courses_only else build_answers(config, channel)
    client = Chaoxing(account=Account(common["username"], common["password"]), tiku=answers,
                      query_delay=config["tiku"]["delay"], work_max_retries=common["work_max_retries"],
                      work_redo_enabled=common["work_redo_enabled"], desktop_mode=True)
    client.desktop_work_lock = threading.Lock()
    return client


def process_job(client, course, job, info, speed):
    kind = job["type"]
    if kind == "video":
        result = client.study_video(course, job, info, _speed=speed, _type="Video")
        return client.study_video(course, job, info, _speed=speed, _type="Audio") if result.is_failure() else result
    if kind == "document":
        return client.study_document(course, job)
    if kind == "read":
        return client.study_read(course, job, info)
    if kind == "workid":
        # Feedback and manual dialogs belong to one exercise at a time.
        with client.desktop_work_lock:
            client.tiku.set_work_feedback(None)
            return client.study_work(course, job, info)
    if kind == "live":
        from api.live import Live
        from api.live_process import LiveProcessor
        live = Live(attachment=job, defaults={"userid": client.get_uid(), "clazzId": course["clazzId"],
                                             "knowledgeid": info.get("knowledgeid")}, course_id=course["courseId"])
        return StudyResult.SUCCESS if LiveProcessor.run_live(live, speed) else StudyResult.ERROR
    return StudyResult.ERROR


def process_chapter(client, course, point, speed):
    if point.get("has_finished"):
        return ChapterResult.SUCCESS
    jobs, info = client.get_job_list(course, point)
    if info.get("notOpen"):
        return ChapterResult.NOT_OPEN
    for job in jobs:
        if process_job(client, course, job, info, speed).is_failure():
            return ChapterResult.ERROR
    return ChapterResult.SUCCESS


def increase_learning_count_for_course(client, course, config):
    points = client.get_course_point(course["courseId"], course["clazzId"], course["cpi"])["points"]
    client.increase_chapter_learning_count(course, points, config["target_count"])
