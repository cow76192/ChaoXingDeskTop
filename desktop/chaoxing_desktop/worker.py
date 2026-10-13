from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
import threading
import time

from .config import Redactor, resource_root, select_courses


class Channel:
    def __init__(self, output, input_stream, redactor):
        self.output, self.input_stream, self.redactor = output, input_stream, redactor
        self.lock = threading.Lock()
        self.input_lock = threading.Lock()

    def send(self, kind: str, **values):
        if "message" in values:
            values["message"] = self.redactor(str(values["message"]))
        with self.lock:
            self.output.write(json.dumps({"type": kind, **values}, ensure_ascii=False) + "\n")
            self.output.flush()

    def ask(self, prompt="", **context):
        with self.input_lock:
            self.send("input", message=prompt, **context)
            line = self.input_stream.readline()
            if not line:
                raise EOFError("交互已取消")
            reply = json.loads(line)
            if reply.get("cancel"):
                # Exit the whole worker: upstream catches EOFError in some manual modes.
                self.send("cancelled", message="用户取消交互，任务停止。")
                self.output.flush()
                os._exit(2)
            return str(reply.get("answer", ""))


class EventStream:
    encoding = "utf-8"
    def __init__(self, channel):
        self.channel = channel

    def write(self, text):
        if text.strip():
            self.channel.send("log", message=text.strip(), level="INFO")
        return len(text)

    def flush(self):
        pass

    def isatty(self):
        return False


def load_core(channel):
    core_path = resource_root() / "vendor/chaoxing"
    sys.path.insert(0, str(core_path))
    # Imports and upstream print calls must never corrupt the JSON protocol.
    sys.stdout = EventStream(channel)
    sys.stderr = EventStream(channel)
    from api.logger import logger
    logger.remove()
    logger.add(lambda msg: channel.send("log", message=msg.record["message"], level=msg.record["level"].name),
               level="INFO", colorize=False, backtrace=False, diagnose=False)
    from . import runtime
    return runtime


def demo(channel, command):
    courses = [dict(courseId="demo-101", clazzId="01", cpi="demo", title="Python 程序设计 · 演示"),
               dict(courseId="demo-102", clazzId="02", cpi="demo", title="大学英语 · 演示"),
               dict(courseId="demo-103", clazzId="03", cpi="demo", title="信息素养 · 演示")]
    channel.send("log", message="离线演示模式：所有课程与任务均为示例，没有连接超星。", level="INFO")
    if command["action"] == "courses":
        time.sleep(0.2)
        channel.send("courses", courses=courses, demo=True)
        return
    chosen = select_courses(courses, command.get("selected", []))
    tasks = [dict(id=f"{c['courseId']}:{i}", course=c["title"], title=t)
             for c in chosen for i, t in enumerate(("01 · 视频学习", "02 · 阅读材料", "03 · 章节练习"))]
    channel.send("tasks", tasks=tasks)
    for task in tasks:
        channel.send("task", id=task["id"], status="running")
        channel.send("log", message=f"正在处理 {task['course']} / {task['title']}", level="INFO")
        time.sleep(0.6)
        channel.send("task", id=task["id"], status="success")
    channel.send("done", success=len(tasks), failed=0, skipped=0, pending=0, demo=True)


def run_tasks(channel, tasks, process, config, result_enum):
    """Bounded chapter scheduling, retry in rounds so dependent chapters can unlock."""
    pending = list(tasks)
    statuses = {}
    for attempt in range(5):
        retry = []
        with ThreadPoolExecutor(max_workers=config["jobs"]) as executor:
            def execute(task):
                channel.send("task", id=task["id"], status="running")
                return process(task)
            futures = {executor.submit(execute, task): task for task in pending}
            for future in as_completed(futures):
                task = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    channel.send("log", message=f"{task['title']}：{type(exc).__name__}: {exc}", level="ERROR")
                    result = result_enum.ERROR
                if result == result_enum.SUCCESS:
                    status = "processed"
                elif result == result_enum.NOT_OPEN:
                    action = config["notopen_action"]
                    if action == "ask":
                        answer = channel.ask(f"章节「{task['title']}」未开放。", kind="choice",
                                             choices=[{"label": "跳过当前章节", "value": "y"},
                                                      {"label": "停止任务", "value": "n"}])
                        if answer.strip().lower() not in ("y", "yes"):
                            channel.send("cancelled", message="用户停止了未开放章节的处理。")
                            os._exit(2)
                    if action in ("ask", "continue"):
                        status = "skipped"
                    elif attempt < 4:
                        status = "retry"
                        retry.append(task)
                    else:
                        status = "skipped"
                elif attempt < 4:
                    status = "retry"
                    retry.append(task)
                else:
                    status = "failed"
                statuses[task["id"]] = status
                channel.send("task", id=task["id"], status=status)
        if not retry:
            break
        channel.send("log", message=f"等待重试 {len(retry)} 个章节（第 {attempt + 2}/5 轮）。", level="WARNING")
        time.sleep(config["retry_interval"])
        pending = retry
    return statuses


def real(channel, command):
    core = load_core(channel)
    common, notification_config = (command["config"][s] for s in ("common", "notification"))
    # Listing courses must not initialize paid question-bank services.
    cx = core.create_client(command["config"], channel, courses_only=command["action"] == "courses")
    login = cx.login(login_with_cookies=common["use_cookies"])
    if not login.get("status"):
        raise RuntimeError(login.get("msg", "登录失败"))
    courses = list({(str(c["courseId"]), str(c["clazzId"])): c for c in cx.get_course_list()}.values())
    if command["action"] == "courses":
        channel.send("courses", courses=courses, demo=False)
        return
    chosen = select_courses(courses, command.get("selected", []))
    tasks = []
    for course in chosen:
        points = cx.get_course_point(course["courseId"], course["clazzId"], course["cpi"])["points"]
        for i, point in enumerate(points):
            tasks.append(dict(id=f"{course['courseId']}:{course['clazzId']}:{point['id']}:{i}",
                              title=point["title"], course=course["title"], course_data=course, point=point))
    channel.send("tasks", tasks=[{k: t[k] for k in ("id", "title", "course")} for t in tasks])
    statuses = run_tasks(channel, tasks,
                         lambda t: core.process_chapter(cx, t["course_data"], t["point"], common["speed"]),
                         common, core.ChapterResult)
    # Re-read platform state: saving answers is not completing an exercise.
    for course in chosen:
        try:
            points = cx.get_course_point(course["courseId"], course["clazzId"], course["cpi"])["points"]
            finished = {str(p["id"]): p.get("has_finished", False) for p in points}
        except Exception as exc:
            channel.send("log", message=f"无法核验章节进度：{exc}", level="WARNING")
            finished = {}
        for task in tasks:
            if task["course_data"] == course and statuses[task["id"]] == "processed":
                status = "success" if finished.get(str(task["point"]["id"]), False) else "pending"
                statuses[task["id"]] = status
                channel.send("task", id=task["id"], status=status)
    if common["add_learning_count"]:
        channel.send("log", message="开始执行章节学习次数追加。", level="INFO")
        for course in chosen:
            core.increase_learning_count_for_course(cx, course, common)
    counts = {s: list(statuses.values()).count(s) for s in ("success", "failed", "skipped", "pending")}
    if notification_config.get("provider"):
        notification = core.Notification()
        notification.config_set(notification_config)
        notification = notification.get_notification_from_config()
        notification.init_notification()
        try:
            notification.send(f"超星桌面版任务结束：{counts}")
        except Exception as exc:
            channel.send("log", message=f"外部通知发送失败：{exc}", level="WARNING")
    channel.send("done", **counts, demo=False)


def main() -> int:
    output, input_stream = sys.stdout, sys.stdin
    if output is None or input_stream is None:
        return 1
    for stream in (output, input_stream):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    command = json.loads(input_stream.readline())
    channel = Channel(output, input_stream, Redactor(command.get("config", {})))
    try:
        path = Path(command["data_dir"]).resolve()
        path.mkdir(parents=True, exist_ok=True)
        os.chdir(path)
        if command.get("action") == "probe":
            load_core(channel)
            from api.cxsecret_font import fonthash_dao
            assert len(fonthash_dao.char_map) > 100, "字体资源缺失"
            channel.send("probe", message="核心导入与字体资源加载正常", font_entries=len(fonthash_dao.char_map))
        elif command.get("action") == "check_ai":
            from .answers import AIClient
            AIClient(command["config"]["ai"]).check_connection()
            channel.send("ai_check")
        elif command.get("demo"):
            demo(channel, command)
        else:
            real(channel, command)
        return 0
    except Exception as exc:
        channel.send("error", message=f"{type(exc).__name__}: {exc}")
        return 1
