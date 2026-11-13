#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Small HTTP server for the Jetbot inspection dashboard.

It serves index.html, starts the integrated inspection orchestrator in a
background thread, and exposes status/report APIs for the frontend.
"""

from __future__ import print_function

import argparse
import json
import os
import posixpath
import shutil
import sys
import threading
import time
import traceback
try:
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
except ImportError:
    try:
        from http.server import SimpleHTTPRequestHandler, HTTPServer
        from socketserver import ThreadingMixIn
    except ImportError:  # Python 2 fallback, not expected on Jetbot notebooks.
        from SimpleHTTPServer import SimpleHTTPRequestHandler
        from SocketServer import ThreadingMixIn
        from BaseHTTPServer import HTTPServer

    class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True


DASHBOARD_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(DASHBOARD_DIR, os.pardir))
ORCHESTRATOR_DIR = os.path.join(PROJECT_DIR, "module_agent_orchestrator")
VOICE_DIR = os.path.join(PROJECT_DIR, "module_voice_control")
DEFAULT_OUTPUT_DIR = os.path.join(ORCHESTRATOR_DIR, "inspection_agent_output")
DEFAULT_KEY_FILES = [
    os.path.join(PROJECT_DIR, "stepfun_api_key.txt"),
    os.path.join(ORCHESTRATOR_DIR, "stepfun_api_key.txt"),
    os.path.join(DASHBOARD_DIR, "stepfun_api_key.txt"),
    os.path.join(PROJECT_DIR, "zhipu_api_key.txt"),
]

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
if ORCHESTRATOR_DIR not in sys.path:
    sys.path.insert(0, ORCHESTRATOR_DIR)
if VOICE_DIR not in sys.path:
    sys.path.insert(0, VOICE_DIR)


STATE_LOCK = threading.Lock()
STATE = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "summary": "idle",
    "stage_status": {
        "anchor": "not_run",
        "search": "not_run",
        "motion": "not_run",
        "feedback": "not_run",
    },
    "report": None,
    "report_path": os.path.join(DEFAULT_OUTPUT_DIR, "inspection_agent_report.json"),
    "error": None,
}


def now_string():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def read_json(path):
    with open(path, "r") as f:
        return json.load(f)


def safe_read_json(path):
    try:
        if os.path.exists(path):
            return read_json(path)
    except Exception:
        return None
    return None


def write_response(handler, status, payload):
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def update_state(**kwargs):
    with STATE_LOCK:
        STATE.update(kwargs)
        return dict(STATE)


def snapshot_state():
    with STATE_LOCK:
        return dict(STATE)


def load_existing_report():
    if snapshot_state().get("running"):
        return
    path = STATE.get("report_path") or os.path.join(DEFAULT_OUTPUT_DIR, "inspection_agent_report.json")
    if os.path.exists(path):
        try:
            report = read_json(path)
            update_state(
                running=False,
                summary=report.get("summary", "report loaded"),
                started_at=report.get("started_at"),
                finished_at=report.get("finished_at"),
                stage_status=report.get("stage_status", {}),
                report=report,
                report_path=path,
                error=None,
            )
        except Exception as exc:
            update_state(error=repr(exc))


def parse_search_decision(search_report):
    parsed = (((search_report or {}).get("vision") or {}).get("parsed") or {})
    return {
        "target_found": parsed.get("target_found"),
        "best_pose": parsed.get("best_pose") or "none",
        "risk_level": parsed.get("risk_level") or "warning",
        "confidence": parsed.get("confidence"),
        "visible_text": parsed.get("visible_text"),
        "inspection_summary": parsed.get("inspection_summary"),
        "next_action": parsed.get("next_action"),
        "reason": parsed.get("reason"),
    }


def update_running_progress():
    state = snapshot_state()
    if not state.get("running"):
        return state

    anchor_path = os.path.join(DEFAULT_OUTPUT_DIR, "01_anchor_approach", "qr_anchor_approach_report.json")
    search_path = os.path.join(DEFAULT_OUTPUT_DIR, "02_target_search", "target_search_report.json")
    motion_path = os.path.join(DEFAULT_OUTPUT_DIR, "03_body_motion", "robot_motion_report.json")
    feedback_path = os.path.join(DEFAULT_OUTPUT_DIR, "04_feedback", "inspection_feedback_report.json")

    anchor_report = safe_read_json(anchor_path)
    search_report = safe_read_json(search_path)
    motion_report = safe_read_json(motion_path)
    feedback_report = safe_read_json(feedback_path)

    stage_status = {
        "anchor": "running",
        "search": "not_run",
        "motion": "not_run",
        "feedback": "not_run",
    }
    decision = {}

    if anchor_report:
        stage_status["anchor"] = "ok" if anchor_report.get("stop_reason") == "target_anchor_reached" else "not_ok"
        stage_status["search"] = "running" if stage_status["anchor"] == "ok" else "not_run"

    if search_report:
        decision = parse_search_decision(search_report)
        stage_status["search"] = "ok" if decision.get("target_found") else "not_ok"
        stage_status["motion"] = "running" if stage_status["search"] == "ok" else "not_run"

    if motion_report:
        event = motion_report.get("event") or {}
        stage_status["motion"] = event.get("status") or "unknown"
        stage_status["feedback"] = "running"

    if feedback_report:
        errors = [event for event in feedback_report.get("events", []) if event.get("status") == "error"]
        stage_status["feedback"] = "error" if errors else "ok"

    partial_report = {
        "demo": "inspection_agent_orchestrator_partial",
        "started_at": state.get("started_at"),
        "finished_at": None,
        "summary": "Inspection is running.",
        "command": None,
        "stage_status": stage_status,
        "decision": decision,
        "anchor_report": anchor_report,
        "search_report": search_report,
        "motion_report": motion_report,
        "feedback_report": feedback_report,
        "report_json": state.get("report_path"),
    }
    return update_state(
        summary="running",
        stage_status=stage_status,
        report=partial_report,
    )


def find_key_file():
    for path in DEFAULT_KEY_FILES:
        if os.path.exists(path):
            return path
    return None


def reset_jetbot_camera_singleton():
    """Best-effort cleanup for long-running dashboard server processes."""
    results = []
    try:
        from jetbot import Camera
        old = getattr(Camera, "_instance", None)
        if old is not None:
            try:
                old.stop()
                results.append({"name": "camera_stop", "ok": True})
            except Exception as exc:
                results.append({"name": "camera_stop", "ok": False, "error": repr(exc)})
        try:
            Camera._instance = None
            results.append({"name": "camera_instance_clear", "ok": True})
        except Exception as exc:
            results.append({"name": "camera_instance_clear", "ok": False, "error": repr(exc)})
    except Exception as exc:
        results.append({"name": "camera_import", "ok": False, "error": repr(exc)})
    return results


def clear_previous_output():
    try:
        if os.path.isdir(DEFAULT_OUTPUT_DIR):
            shutil.rmtree(DEFAULT_OUTPUT_DIR)
        os.makedirs(DEFAULT_OUTPUT_DIR)
        return {"ok": True, "path": DEFAULT_OUTPUT_DIR}
    except Exception as exc:
        return {"ok": False, "path": DEFAULT_OUTPUT_DIR, "error": repr(exc)}


def speak_initialization_done():
    event = {
        "time": now_string(),
        "type": "voice_initialization_done",
        "status": "not_run",
    }
    try:
        import voice_control_tool
        module = voice_control_tool.VoiceControl()
        try:
            event["opened"] = module.open()
            event["broadcast"] = module.speak("legacy_init")
            event["status"] = "executed"
        finally:
            module.close()
    except Exception as exc:
        event["status"] = "error"
        event["error"] = repr(exc)
    return event


def run_inspection(command, enable_motion):
    previous_cwd = os.getcwd()
    update_state(
        running=True,
        started_at=now_string(),
        finished_at=None,
        summary="running",
        stage_status={
            "anchor": "running",
            "search": "not_run",
            "motion": "not_run",
            "feedback": "not_run",
        },
        report=None,
        error=None,
    )
    try:
        os.chdir(PROJECT_DIR)
        clear_output = clear_previous_output()
        camera_reset = reset_jetbot_camera_singleton()
        init_voice = speak_initialization_done()
        import inspection_agent_orchestrator

        key_file = find_key_file()
        report = inspection_agent_orchestrator.run_demo(
            output_dir=DEFAULT_OUTPUT_DIR,
            command=command,
            enable_motion=bool(enable_motion),
            key_file=key_file,
        )
        report["dashboard_preflight"] = {
            "working_dir": PROJECT_DIR,
            "key_file": key_file,
            "camera_reset": camera_reset,
            "clear_output": clear_output,
            "init_voice": init_voice,
        }
        try:
            report_path = report.get("report_json") or os.path.join(DEFAULT_OUTPUT_DIR, "inspection_agent_report.json")
            with open(report_path, "w") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        update_state(
            running=False,
            finished_at=now_string(),
            summary=report.get("summary", "completed"),
            stage_status=report.get("stage_status", {}),
            report=report,
            report_path=report.get("report_json") or os.path.join(DEFAULT_OUTPUT_DIR, "inspection_agent_report.json"),
            error=report.get("error"),
        )
    except Exception as exc:
        update_state(
            running=False,
            finished_at=now_string(),
            summary="error",
            error=repr(exc),
            report={
                "summary": "Error: {0}".format(repr(exc)),
                "error": repr(exc),
                "traceback": traceback.format_exc(),
                "stage_status": snapshot_state().get("stage_status", {}),
            },
        )
    finally:
        try:
            os.chdir(previous_cwd)
        except Exception:
            pass


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        try:
            super(DashboardHandler, self).__init__(*args, directory=DASHBOARD_DIR, **kwargs)
        except TypeError:
            os.chdir(DASHBOARD_DIR)
            SimpleHTTPRequestHandler.__init__(self, *args, **kwargs)

    def log_message(self, fmt, *args):
        print("[%s] %s" % (now_string(), fmt % args))

    def do_GET(self):
        route = self.path.split("?", 1)[0]
        if route == "/api/status":
            if snapshot_state().get("running"):
                update_running_progress()
            else:
                load_existing_report()
            write_response(self, 200, snapshot_state())
            return
        if route == "/api/report":
            load_existing_report()
            state = snapshot_state()
            if state.get("report"):
                write_response(self, 200, state["report"])
            else:
                write_response(self, 404, {"error": "No report available."})
            return
        if route.startswith("/outputs/"):
            self.serve_output_file(route[len("/outputs/"):])
            return
        if route == "/":
            self.path = "/index.html"
        return SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        route = self.path.split("?", 1)[0]
        if route != "/api/start":
            write_response(self, 404, {"error": "Unknown endpoint."})
            return

        state = snapshot_state()
        if state.get("running"):
            write_response(self, 409, {"error": "Inspection is already running.", "state": state})
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            body = {}
        command = body.get("command") or "开始 A01 工位巡检"
        enable_motion = bool(body.get("enable_motion", True))
        worker = threading.Thread(target=run_inspection, args=(command, enable_motion))
        worker.daemon = True
        worker.start()
        write_response(self, 202, snapshot_state())

    def serve_output_file(self, rel_path):
        rel_path = posixpath.normpath(rel_path).lstrip("/")
        fs_path = os.path.abspath(os.path.join(PROJECT_DIR, rel_path.replace("/", os.sep)))
        if not fs_path.startswith(PROJECT_DIR):
            self.send_error(403)
            return
        if not os.path.exists(fs_path):
            self.send_error(404)
            return
        self.path = fs_path
        return self.send_file_path(fs_path)

    def send_file_path(self, fs_path):
        ctype = self.guess_type(fs_path)
        try:
            with open(fs_path, "rb") as f:
                data = f.read()
        except IOError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8060)
    args = parser.parse_args(argv)

    load_existing_report()
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print("Dashboard: http://{0}:{1}".format(args.host, args.port))
    print("Open from Jetbot browser/Jupyter host as: http://<jetbot-ip>:{0}".format(args.port))
    server.serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
