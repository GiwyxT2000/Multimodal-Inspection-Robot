#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integrated inspection agent orchestrator for Yahboom Jetbot.

This module does not implement low-level robot capabilities directly. It calls
the tested tool modules in sequence:

1. Anchor approach / station confirmation.
2. Gimbal target search and multimodal inspection.
3. Chassis alignment toward the target sign.
4. Buzzer and RGB feedback by risk level.
"""

from __future__ import print_function

import argparse
import codecs
import json
import os
import sys
import time
import traceback


PARENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

MODULE_DIRS = [
    PARENT_DIR,
    os.path.join(PARENT_DIR, "module_target_search"),
    os.path.join(PARENT_DIR, "module_motion_tool"),
    os.path.join(PARENT_DIR, "module_feedback_tool"),
    os.path.join(PARENT_DIR, "module_voice_control"),
]
for path in MODULE_DIRS:
    if path not in sys.path:
        sys.path.insert(0, path)

import qr_anchor_approach_demo as anchor_tool  # noqa: E402
import target_search_tool  # noqa: E402
import robot_motion_tool  # noqa: E402
import inspection_feedback_tool  # noqa: E402
try:
    import voice_control_tool  # noqa: E402
except Exception:
    voice_control_tool = None


DEFAULT_OUTPUT_DIR = "inspection_agent_output"
DEFAULT_COMMAND = "寮€濮婣01宸ヤ綅宸℃"
DEFAULT_MODEL = "step-3.7-flash"


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


def anchor_succeeded(anchor_report):
    if not anchor_report:
        return False
    return anchor_report.get("stop_reason") == "target_anchor_reached"


def parse_search_decision(search_report):
    parsed = ((search_report.get("vision") or {}).get("parsed") or {})
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


def compact_kwargs(kwargs):
    return dict((key, value) for key, value in kwargs.items() if value is not None)


def module_audit():
    return {
        "anchor_tool": {
            "file": getattr(anchor_tool, "__file__", None),
            "step_duration": getattr(anchor_tool, "DEFAULT_STEP_DURATION", None),
            "fine_step_duration": getattr(anchor_tool, "DEFAULT_FINE_STEP_DURATION", None),
            "micro_step_duration": getattr(anchor_tool, "DEFAULT_MICRO_STEP_DURATION", None),
        },
        "target_search_tool": {
            "file": getattr(target_search_tool, "__file__", None),
            "search_profile": getattr(target_search_tool, "DEFAULT_SEARCH_PROFILE", None),
            "pan_delta": getattr(target_search_tool, "DEFAULT_PAN_DELTA", None),
            "max_tokens": getattr(target_search_tool, "DEFAULT_MAX_TOKENS", None),
        },
        "robot_motion_tool": {
            "file": getattr(robot_motion_tool, "__file__", None),
            "turn_speed": getattr(robot_motion_tool, "DEFAULT_TURN_SPEED", None),
            "turn_duration": getattr(robot_motion_tool, "DEFAULT_TURN_DURATION", None),
            "kick_duration": getattr(robot_motion_tool, "DEFAULT_KICK_DURATION", None),
        },
        "inspection_feedback_tool": {
            "file": getattr(inspection_feedback_tool, "__file__", None),
            "rgb_loops": getattr(inspection_feedback_tool, "DEFAULT_RGB_LOOPS", None),
            "rgb_blink_count": getattr(inspection_feedback_tool, "DEFAULT_RGB_BLINK_COUNT", None),
            "rgb_blink_on": getattr(inspection_feedback_tool, "DEFAULT_RGB_BLINK_ON", None),
            "rgb_blink_off": getattr(inspection_feedback_tool, "DEFAULT_RGB_BLINK_OFF", None),
        },
        "voice_control_tool": {
            "file": getattr(voice_control_tool, "__file__", None) if voice_control_tool else None,
            "available": bool(voice_control_tool),
        },
    }


def voice_broadcast_risk(risk_level):
    event = {
        "time": now_string(),
        "type": "voice_broadcast",
        "risk_level": risk_level,
        "status": "not_available",
    }
    if voice_control_tool is None:
        event["error"] = "voice_control_tool is not available"
        return event
    module = None
    try:
        module = voice_control_tool.VoiceControl()
        opened = module.open()
        event["opened"] = opened
        event["broadcast"] = module.speak_risk(risk_level)
        event["status"] = "executed"
    except Exception as exc:
        event["status"] = "error"
        event["error"] = repr(exc)
    finally:
        if module is not None:
            module.close()
    return event


def write_text_report(report, path):
    lines = []
    lines.append("Integrated Inspection Agent")
    lines.append("Time: {0} -> {1}".format(report.get("started_at"), report.get("finished_at")))
    lines.append("Summary: {0}".format(report.get("summary")))
    lines.append("Command: {0}".format(report.get("command")))
    lines.append("")
    lines.append("== Stage Status ==")
    lines.append(json.dumps(report.get("stage_status", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Decision ==")
    lines.append(json.dumps(report.get("decision", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Config ==")
    lines.append(json.dumps(report.get("config", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Module Audit ==")
    lines.append(json.dumps(report.get("module_audit", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Report Paths ==")
    for key, value in sorted((report.get("report_paths") or {}).items()):
        lines.append("{0}: {1}".format(key, value))
    if report.get("error"):
        lines.append("")
        lines.append("== Error ==")
        lines.append(report.get("error"))
        lines.append("")
        lines.append("== Traceback ==")
        lines.append(report.get("traceback") or "")
    write_text(path, "\n".join(lines))


def summarize_report(report):
    decision = report.get("decision") or {}
    lines = []
    lines.append("Integrated Inspection Agent")
    lines.append("Summary: {0}".format(report.get("summary")))
    lines.append("anchor: {0}".format((report.get("stage_status") or {}).get("anchor")))
    lines.append("search: {0}".format((report.get("stage_status") or {}).get("search")))
    lines.append("motion: {0}".format((report.get("stage_status") or {}).get("motion")))
    lines.append("feedback: {0}".format((report.get("stage_status") or {}).get("feedback")))
    lines.append("Best pose: {0}".format(decision.get("best_pose")))
    lines.append("Risk level: {0}".format(decision.get("risk_level")))
    lines.append("JSON report: {0}".format(report.get("report_json")))
    lines.append("Text report: {0}".format(report.get("report_txt")))
    return "\n".join(lines)


def run_demo(output_dir=DEFAULT_OUTPUT_DIR,
             command=DEFAULT_COMMAND,
             model=None,
             api_key=None,
             key_file=None,
             enable_motion=False,
             run_anchor=True,
             run_search=True,
             run_motion=True,
             run_feedback=True,
             require_anchor_success=True,
             require_target_found=True,
             anchor_strategy="opencv_qr",
             anchor_enable_motion=None,
             anchor_step_speed=None,
             anchor_step_duration=None,
             anchor_fine_step_speed=None,
             anchor_fine_step_duration=None,
             anchor_late_step_duration=None,
             anchor_slow_after_steps=None,
             anchor_micro_step_speed=None,
             anchor_micro_step_duration=None,
             anchor_micro_width_ratio=None,
             anchor_motor_kick_speed=None,
             anchor_motor_kick_duration=None,
             anchor_enable_backoff=None,
             anchor_backoff_width_ratio=None,
             anchor_backoff_speed=None,
             anchor_backoff_duration=None,
             anchor_max_steps=None,
             anchor_max_missing_steps=None,
             search_profile=None,
             target_text=None,
             home_pan=None,
             home_tilt=None,
             pan_delta=None,
             tilt_up_delta=None,
             tilt_down_delta=None,
             search_max_tokens=None,
             motion_turn_speed=None,
             motion_turn_duration=None,
             motion_kick_speed=None,
             motion_kick_duration=None,
             feedback_beep_on=None,
             feedback_beep_off=None,
             feedback_rgb_loops=None,
             feedback_rgb_blink_count=None,
             feedback_rgb_blink_on=None,
             feedback_rgb_blink_off=None,
             feedback_rgb_off_at_end=None,
             default_risk_level="warning"):
    ensure_dir(output_dir)
    started_at = now_string()
    if anchor_enable_motion is None:
        anchor_enable_motion = enable_motion

    report = {
        "demo": "inspection_agent_orchestrator",
        "started_at": started_at,
        "finished_at": None,
        "summary": "running",
        "command": command,
        "config": {
            "output_dir": output_dir,
            "command": command,
            "model": model,
            "enable_motion": enable_motion,
            "run_anchor": run_anchor,
            "run_search": run_search,
            "run_motion": run_motion,
            "run_feedback": run_feedback,
            "require_anchor_success": require_anchor_success,
            "require_target_found": require_target_found,
            "anchor_strategy": anchor_strategy,
            "anchor_enable_motion": anchor_enable_motion,
            "anchor_step_speed": anchor_step_speed,
            "anchor_step_duration": anchor_step_duration,
            "anchor_fine_step_speed": anchor_fine_step_speed,
            "anchor_fine_step_duration": anchor_fine_step_duration,
            "anchor_late_step_duration": anchor_late_step_duration,
            "anchor_slow_after_steps": anchor_slow_after_steps,
            "anchor_micro_step_speed": anchor_micro_step_speed,
            "anchor_micro_step_duration": anchor_micro_step_duration,
            "anchor_micro_width_ratio": anchor_micro_width_ratio,
            "anchor_motor_kick_speed": anchor_motor_kick_speed,
            "anchor_motor_kick_duration": anchor_motor_kick_duration,
            "anchor_enable_backoff": anchor_enable_backoff,
            "search_profile": search_profile,
            "target_text": target_text,
            "home_pan": home_pan,
            "home_tilt": home_tilt,
            "pan_delta": pan_delta,
            "tilt_up_delta": tilt_up_delta,
            "tilt_down_delta": tilt_down_delta,
            "search_max_tokens": search_max_tokens,
            "motion_turn_speed": motion_turn_speed,
            "motion_turn_duration": motion_turn_duration,
            "motion_kick_speed": motion_kick_speed,
            "motion_kick_duration": motion_kick_duration,
            "feedback_beep_on": feedback_beep_on,
            "feedback_beep_off": feedback_beep_off,
            "feedback_rgb_loops": feedback_rgb_loops,
            "feedback_rgb_blink_count": feedback_rgb_blink_count,
            "feedback_rgb_blink_on": feedback_rgb_blink_on,
            "feedback_rgb_blink_off": feedback_rgb_blink_off,
            "feedback_rgb_off_at_end": feedback_rgb_off_at_end,
            "default_risk_level": default_risk_level,
        },
        "module_audit": module_audit(),
        "stage_status": {
            "anchor": "not_run",
            "search": "not_run",
            "motion": "not_run",
            "feedback": "not_run",
        },
        "decision": {},
        "report_paths": {},
        "anchor_report": None,
        "search_report": None,
        "motion_report": None,
        "feedback_report": None,
        "voice_report": None,
        "error": None,
        "traceback": None,
    }

    try:
        if run_anchor:
            if anchor_strategy != "opencv_qr":
                raise RuntimeError("Unsupported anchor_strategy: {0}".format(anchor_strategy))
            anchor_dir = os.path.join(output_dir, "01_anchor_approach")
            anchor_kwargs = compact_kwargs({
                "home_pan": home_pan,
                "home_tilt": home_tilt,
                "step_speed": anchor_step_speed,
                "step_duration": anchor_step_duration,
                "fine_step_speed": anchor_fine_step_speed,
                "fine_step_duration": anchor_fine_step_duration,
                "late_step_duration": anchor_late_step_duration,
                "slow_after_steps": anchor_slow_after_steps,
                "micro_step_speed": anchor_micro_step_speed,
                "micro_step_duration": anchor_micro_step_duration,
                "micro_width_ratio": anchor_micro_width_ratio,
                "motor_kick_speed": anchor_motor_kick_speed,
                "motor_kick_duration": anchor_motor_kick_duration,
                "enable_backoff": anchor_enable_backoff,
                "backoff_width_ratio": anchor_backoff_width_ratio,
                "backoff_speed": anchor_backoff_speed,
                "backoff_duration": anchor_backoff_duration,
                "max_steps": anchor_max_steps,
                "max_missing_steps": anchor_max_missing_steps,
            })
            anchor_report = anchor_tool.run_demo(
                output_dir=anchor_dir,
                prepare=True,
                init_gimbal=True,
                require_gimbal=True,
                enable_motion=anchor_enable_motion,
                save_frames=True,
                **anchor_kwargs
            )
            report["anchor_report"] = anchor_report
            report["report_paths"]["anchor_json"] = anchor_report.get("report_json")
            report["report_paths"]["anchor_txt"] = anchor_report.get("report_txt")
            report["stage_status"]["anchor"] = "ok" if anchor_succeeded(anchor_report) else "not_ok"
            if require_anchor_success and not anchor_succeeded(anchor_report):
                report["summary"] = "Stopped after anchor stage; stop-anchor was not confirmed."
                return finalize_report(report, output_dir)
        else:
            report["stage_status"]["anchor"] = "skipped"

        if run_search:
            search_dir = os.path.join(output_dir, "02_target_search")
            search_kwargs = compact_kwargs({
                "target_text": target_text,
                "api_key": api_key,
                "key_file": key_file,
                "model": model,
                "home_pan": home_pan,
                "home_tilt": home_tilt,
                "pan_delta": pan_delta,
                "tilt_up_delta": tilt_up_delta,
                "tilt_down_delta": tilt_down_delta,
                "search_profile": search_profile,
                "max_tokens": search_max_tokens,
            })
            search_report = target_search_tool.run_demo(
                output_dir=search_dir,
                reasoning_effort="low",
                return_to_home=True,
                **search_kwargs
            )
            report["search_report"] = search_report
            report["report_paths"]["search_json"] = search_report.get("report_json")
            report["report_paths"]["search_txt"] = search_report.get("report_txt")
            decision = parse_search_decision(search_report)
            report["decision"].update(decision)
            report["stage_status"]["search"] = "ok" if decision.get("target_found") else "not_ok"
            if require_target_found and not decision.get("target_found"):
                report["summary"] = "Stopped after search stage; target sign was not found."
                return finalize_report(report, output_dir)
        else:
            report["stage_status"]["search"] = "skipped"
            report["decision"].setdefault("best_pose", "center")
            report["decision"].setdefault("risk_level", default_risk_level)

        best_pose = report["decision"].get("best_pose") or "center"
        risk_level = report["decision"].get("risk_level") or default_risk_level

        if run_motion:
            motion_dir = os.path.join(output_dir, "03_body_motion")
            motion_kwargs = compact_kwargs({
                "turn_speed": motion_turn_speed,
                "turn_duration": motion_turn_duration,
                "kick_speed": motion_kick_speed,
                "kick_duration": motion_kick_duration,
            })
            motion_report = robot_motion_tool.run_demo(
                output_dir=motion_dir,
                action="align",
                best_pose=best_pose,
                enable_motion=enable_motion,
                **motion_kwargs
            )
            report["motion_report"] = motion_report
            report["report_paths"]["motion_json"] = motion_report.get("report_json")
            report["report_paths"]["motion_txt"] = motion_report.get("report_txt")
            event = motion_report.get("event") or {}
            report["stage_status"]["motion"] = event.get("status") or "unknown"
        else:
            report["stage_status"]["motion"] = "skipped"

        voice_report = voice_broadcast_risk(risk_level)
        report["voice_report"] = voice_report

        if run_feedback:
            feedback_dir = os.path.join(output_dir, "04_feedback")
            feedback_kwargs = compact_kwargs({
                "beep_on": feedback_beep_on,
                "beep_off": feedback_beep_off,
                "rgb_loops": feedback_rgb_loops,
                "rgb_blink_count": feedback_rgb_blink_count,
                "rgb_blink_on": feedback_rgb_blink_on,
                "rgb_blink_off": feedback_rgb_blink_off,
                "rgb_off_at_end": feedback_rgb_off_at_end,
            })
            feedback_report = inspection_feedback_tool.run_demo(
                output_dir=feedback_dir,
                risk_level=risk_level,
                enable_buzzer=True,
                enable_rgb=True,
                **feedback_kwargs
            )
            report["feedback_report"] = feedback_report
            report["report_paths"]["feedback_json"] = feedback_report.get("report_json")
            report["report_paths"]["feedback_txt"] = feedback_report.get("report_txt")
            errors = [event for event in feedback_report.get("events", []) if event.get("status") == "error"]
            report["stage_status"]["feedback"] = "error" if errors else "ok"
        else:
            report["stage_status"]["feedback"] = "skipped"

        report["summary"] = "Integrated inspection flow completed."
        return finalize_report(report, output_dir)
    except Exception as exc:
        report["summary"] = "Error: {0}".format(repr(exc))
        report["error"] = repr(exc)
        report["traceback"] = traceback.format_exc()
        return finalize_report(report, output_dir)


def finalize_report(report, output_dir):
    report["finished_at"] = now_string()
    json_path = os.path.join(output_dir, "inspection_agent_report.json")
    text_path = os.path.join(output_dir, "inspection_agent_report.txt")
    report["report_json"] = json_path
    report["report_txt"] = text_path
    write_json(json_path, report)
    write_text_report(report, text_path)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--command", default=DEFAULT_COMMAND)
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--key-file", default=None)
    parser.add_argument("--enable-motion", action="store_true")
    parser.add_argument("--skip-anchor", action="store_true")
    parser.add_argument("--skip-search", action="store_true")
    parser.add_argument("--skip-motion", action="store_true")
    parser.add_argument("--skip-feedback", action="store_true")
    parser.add_argument("--allow-anchor-failure", action="store_true")
    parser.add_argument("--allow-target-missing", action="store_true")
    parser.add_argument("--search-profile", default=None,
                        choices=["front_sign", "front_sign_wide"])
    parser.add_argument("--pan-delta", type=int, default=None)
    parser.add_argument("--motion-turn-speed", type=float, default=None)
    parser.add_argument("--motion-turn-duration", type=float, default=None)
    parser.add_argument("--motion-kick-speed", type=float, default=None)
    parser.add_argument("--motion-kick-duration", type=float, default=None)
    parser.add_argument("--feedback-beep-on", type=float, default=None)
    parser.add_argument("--feedback-beep-off", type=float, default=None)
    parser.add_argument("--feedback-rgb-loops", type=int, default=None)
    parser.add_argument("--feedback-rgb-blink-count", type=int, default=None)
    parser.add_argument("--feedback-rgb-blink-on", type=float, default=None)
    parser.add_argument("--feedback-rgb-blink-off", type=float, default=None)
    args = parser.parse_args(argv)

    report = run_demo(
        output_dir=args.output_dir,
        command=args.command,
        model=args.model,
        api_key=args.api_key,
        key_file=args.key_file,
        enable_motion=args.enable_motion,
        run_anchor=(not args.skip_anchor),
        run_search=(not args.skip_search),
        run_motion=(not args.skip_motion),
        run_feedback=(not args.skip_feedback),
        require_anchor_success=(not args.allow_anchor_failure),
        require_target_found=(not args.allow_target_missing),
        search_profile=args.search_profile,
        pan_delta=args.pan_delta,
        motion_turn_speed=args.motion_turn_speed,
        motion_turn_duration=args.motion_turn_duration,
        motion_kick_speed=args.motion_kick_speed,
        motion_kick_duration=args.motion_kick_duration,
        feedback_beep_on=args.feedback_beep_on,
        feedback_beep_off=args.feedback_beep_off,
        feedback_rgb_loops=args.feedback_rgb_loops,
        feedback_rgb_blink_count=args.feedback_rgb_blink_count,
        feedback_rgb_blink_on=args.feedback_rgb_blink_on,
        feedback_rgb_blink_off=args.feedback_rgb_blink_off,
    )
    print(summarize_report(report))
    return 0 if not report.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
