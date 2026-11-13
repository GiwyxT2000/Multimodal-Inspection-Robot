#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Robot chassis motion tool for Yahboom Jetbot.

This module only controls the robot chassis. It does not use the camera,
gimbal, QR detector, VLM, buzzer, or RGB strip.
"""

from __future__ import print_function

import argparse
import codecs
import json
import os
import time
import traceback


DEFAULT_OUTPUT_DIR = "robot_motion_output"
DEFAULT_MOVE_SPEED = 0.45
DEFAULT_MOVE_DURATION = 0.35
DEFAULT_TURN_SPEED = 0.45
DEFAULT_TURN_DURATION = 0.80
DEFAULT_KICK_SPEED = 0.75
DEFAULT_KICK_DURATION = 0.08


def now_string():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def ensure_dir(path):
    if path and not os.path.exists(path):
        os.makedirs(path)


def write_json(path, data):
    with codecs.open(path, "w", "utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_text(path, text):
    with codecs.open(path, "w", "utf-8") as f:
        f.write(text)


def init_robot():
    from jetbot import Robot
    robot = Robot()
    robot.stop()
    return robot


def best_pose_to_turn_action(best_pose):
    pose = (best_pose or "").strip().lower()
    if not pose or pose == "none":
        return "none"
    if "left" in pose:
        return "left"
    if "right" in pose:
        return "right"
    return "none"


def run_motion(action="stop",
               speed=DEFAULT_MOVE_SPEED,
               duration=DEFAULT_MOVE_DURATION,
               kick_speed=DEFAULT_KICK_SPEED,
               kick_duration=DEFAULT_KICK_DURATION,
               enable_motion=False):
    action = (action or "stop").strip().lower()
    event = {
        "time": now_string(),
        "type": "motion",
        "action": action,
        "speed": speed,
        "duration": duration,
        "kick_speed": kick_speed,
        "kick_duration": kick_duration,
        "enable_motion": bool(enable_motion),
    }

    allowed = {
        "forward": "forward",
        "backward": "backward",
        "left": "left",
        "right": "right",
        "stop": "stop",
        "none": "none",
    }
    if action not in allowed:
        event["status"] = "error"
        event["error"] = "unsupported action: {0}".format(action)
        return event

    if action in ["none", "stop"]:
        event["status"] = "skipped" if action == "none" else "executed"
        event["reason"] = "no chassis movement required" if action == "none" else "stop command"
        if action == "stop" and enable_motion:
            robot = None
            try:
                robot = init_robot()
                robot.stop()
            finally:
                try:
                    if robot is not None:
                        robot.stop()
                except Exception:
                    pass
        return event

    if not enable_motion:
        event["status"] = "dry_run"
        event["reason"] = "enable_motion is false"
        return event

    robot = None
    try:
        robot = init_robot()
        move = getattr(robot, allowed[action])
        robot.stop()
        if float(kick_duration) > 0:
            move(float(kick_speed))
            time.sleep(float(kick_duration))
        move(float(speed))
        time.sleep(float(duration))
        robot.stop()
        event["status"] = "executed"
    except Exception as exc:
        event["status"] = "error"
        event["error"] = repr(exc)
        event["traceback"] = traceback.format_exc()
    finally:
        try:
            if robot is not None:
                robot.stop()
        except Exception:
            pass
    return event


def align_body_to_best_pose(best_pose="center",
                            enable_motion=False,
                            turn_speed=DEFAULT_TURN_SPEED,
                            turn_duration=DEFAULT_TURN_DURATION,
                            kick_speed=DEFAULT_KICK_SPEED,
                            kick_duration=DEFAULT_KICK_DURATION):
    action = best_pose_to_turn_action(best_pose)
    event = run_motion(
        action=action,
        speed=turn_speed,
        duration=turn_duration,
        kick_speed=kick_speed,
        kick_duration=kick_duration,
        enable_motion=enable_motion,
    )
    event["type"] = "align_body_to_best_pose"
    event["best_pose"] = best_pose
    event["mapped_action"] = action
    return event


def write_text_report(report, path):
    lines = []
    lines.append("Robot Motion Tool")
    lines.append("Time: {0} -> {1}".format(report.get("started_at"), report.get("finished_at")))
    lines.append("Summary: {0}".format(report.get("summary")))
    lines.append("")
    lines.append("== Config ==")
    lines.append(json.dumps(report.get("config", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Event ==")
    lines.append(json.dumps(report.get("event", {}), ensure_ascii=False, indent=2))
    if report.get("error"):
        lines.append("")
        lines.append("== Error ==")
        lines.append(report.get("error"))
    write_text(path, "\n".join(lines))


def summarize_report(report):
    event = report.get("event") or {}
    lines = []
    lines.append("Robot Motion Tool")
    lines.append("Summary: {0}".format(report.get("summary")))
    lines.append("Action: {0}".format(event.get("action")))
    lines.append("Status: {0}".format(event.get("status")))
    lines.append("Best pose: {0}".format(event.get("best_pose")))
    lines.append("JSON report: {0}".format(report.get("report_json")))
    lines.append("Text report: {0}".format(report.get("report_txt")))
    return "\n".join(lines)


def run_demo(output_dir=DEFAULT_OUTPUT_DIR,
             action="align",
             best_pose="center",
             enable_motion=False,
             move_speed=DEFAULT_MOVE_SPEED,
             move_duration=DEFAULT_MOVE_DURATION,
             turn_speed=DEFAULT_TURN_SPEED,
             turn_duration=DEFAULT_TURN_DURATION,
             kick_speed=DEFAULT_KICK_SPEED,
             kick_duration=DEFAULT_KICK_DURATION):
    ensure_dir(output_dir)
    started_at = now_string()
    report = {
        "demo": "robot_motion_tool",
        "started_at": started_at,
        "finished_at": None,
        "summary": "running",
        "config": {
            "output_dir": output_dir,
            "action": action,
            "best_pose": best_pose,
            "enable_motion": enable_motion,
            "move_speed": move_speed,
            "move_duration": move_duration,
            "turn_speed": turn_speed,
            "turn_duration": turn_duration,
            "kick_speed": kick_speed,
            "kick_duration": kick_duration,
        },
        "event": None,
        "error": None,
    }

    try:
        if action == "align":
            report["event"] = align_body_to_best_pose(
                best_pose=best_pose,
                enable_motion=enable_motion,
                turn_speed=turn_speed,
                turn_duration=turn_duration,
                kick_speed=kick_speed,
                kick_duration=kick_duration,
            )
        else:
            report["event"] = run_motion(
                action=action,
                speed=move_speed if action in ["forward", "backward"] else turn_speed,
                duration=move_duration if action in ["forward", "backward"] else turn_duration,
                kick_speed=kick_speed,
                kick_duration=kick_duration,
                enable_motion=enable_motion,
            )

        status = (report["event"] or {}).get("status")
        if status == "executed":
            report["summary"] = "Motion executed."
        elif status == "dry_run":
            report["summary"] = "Dry run completed."
        elif status == "skipped":
            report["summary"] = "No chassis movement required."
        else:
            report["summary"] = "Motion finished with status: {0}".format(status)
    except Exception as exc:
        report["summary"] = "Error: {0}".format(repr(exc))
        report["error"] = repr(exc)
    finally:
        report["finished_at"] = now_string()

    json_path = os.path.join(output_dir, "robot_motion_report.json")
    text_path = os.path.join(output_dir, "robot_motion_report.txt")
    report["report_json"] = json_path
    report["report_txt"] = text_path
    write_json(json_path, report)
    write_text_report(report, text_path)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--action", default="align",
                        choices=["align", "forward", "backward", "left", "right", "stop", "none"])
    parser.add_argument("--best-pose", default="center")
    parser.add_argument("--enable-motion", action="store_true")
    parser.add_argument("--move-speed", type=float, default=DEFAULT_MOVE_SPEED)
    parser.add_argument("--move-duration", type=float, default=DEFAULT_MOVE_DURATION)
    parser.add_argument("--turn-speed", type=float, default=DEFAULT_TURN_SPEED)
    parser.add_argument("--turn-duration", type=float, default=DEFAULT_TURN_DURATION)
    parser.add_argument("--kick-speed", type=float, default=DEFAULT_KICK_SPEED)
    parser.add_argument("--kick-duration", type=float, default=DEFAULT_KICK_DURATION)
    args = parser.parse_args(argv)

    report = run_demo(
        output_dir=args.output_dir,
        action=args.action,
        best_pose=args.best_pose,
        enable_motion=args.enable_motion,
        move_speed=args.move_speed,
        move_duration=args.move_duration,
        turn_speed=args.turn_speed,
        turn_duration=args.turn_duration,
        kick_speed=args.kick_speed,
        kick_duration=args.kick_duration,
    )
    print(summarize_report(report))
    return 0 if not report.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
