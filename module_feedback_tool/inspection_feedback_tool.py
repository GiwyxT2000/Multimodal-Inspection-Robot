#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inspection feedback tool for Yahboom Jetbot.

This module only provides risk-level physical feedback:
1. Buzzer pattern.
2. RGB strip color/flow/blink pattern.

It does not move the robot chassis and does not use the camera, gimbal, QR
detector, or multimodal model.
"""

from __future__ import print_function

import argparse
import glob
import importlib.util
import json
import os
import time
import traceback


DEFAULT_OUTPUT_DIR = "inspection_feedback_output"
DEFAULT_BEEP_PIN = 6
DEFAULT_BEEP_ON = 0.80
DEFAULT_BEEP_OFF = 0.30
DEFAULT_RGB_LED_COUNT = 10
DEFAULT_RGB_LOOPS = 2
DEFAULT_RGB_STEP_DELAY = 0.08
DEFAULT_RGB_BLINK_COUNT = 5
DEFAULT_RGB_BLINK_ON = 0.35
DEFAULT_RGB_BLINK_OFF = 0.25

RISK_COLORS = {
    "normal": (0x00, 0x80, 0x20),
    "warning": (0xFF, 0xB0, 0x00),
    "abnormal": (0xFF, 0x00, 0x00),
}

RISK_BEEP_COUNTS = {
    "normal": 1,
    "warning": 2,
    "abnormal": 3,
}

RISK_ALIASES = {
    "ok": "normal",
    "safe": "normal",
    "normal": "normal",
    "low": "normal",
    "正常": "normal",
    "低": "normal",
    "medium": "warning",
    "warn": "warning",
    "warning": "warning",
    "警告": "warning",
    "中": "warning",
    "high": "abnormal",
    "danger": "abnormal",
    "abnormal": "abnormal",
    "异常": "abnormal",
    "高": "abnormal",
}


def now_string():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def ensure_dir(path):
    if path and not os.path.exists(path):
        os.makedirs(path)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def normalize_risk_level(risk_level):
    key = (risk_level or "warning").strip().lower()
    return RISK_ALIASES.get(key, "warning")


def color_to_hex(color):
    return "#{0:02X}{1:02X}{2:02X}".format(color[0], color[1], color[2])


def load_search_risk_level(path):
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        report = json.load(f)
    parsed = ((report.get("vision") or {}).get("parsed") or {})
    if not parsed:
        parsed = ((report.get("vision_result") or {}).get("parsed") or {})
    return {
        "source_path": path,
        "target_found": parsed.get("target_found"),
        "best_pose": parsed.get("best_pose"),
        "risk_level": parsed.get("risk_level") or parsed.get("risk") or parsed.get("status"),
        "inspection_summary": parsed.get("inspection_summary"),
    }


def run_buzzer_pattern(risk_level="warning", enable_buzzer=True,
                       beep_pin=DEFAULT_BEEP_PIN,
                       beep_on=DEFAULT_BEEP_ON,
                       beep_off=DEFAULT_BEEP_OFF):
    level = normalize_risk_level(risk_level)
    count = RISK_BEEP_COUNTS.get(level, 2)
    event = {
        "time": now_string(),
        "type": "buzzer",
        "risk_level": level,
        "beep_count": count,
        "beep_pin": beep_pin,
        "beep_on": beep_on,
        "beep_off": beep_off,
        "enable_buzzer": bool(enable_buzzer),
        "volume_note": "GPIO active buzzer volume is hardware-limited; HIGH output is already the maximum software drive.",
    }
    if not enable_buzzer:
        event["status"] = "skipped"
        return event

    try:
        import RPi.GPIO as GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(int(beep_pin), GPIO.OUT, initial=GPIO.LOW)
        for _ in range(count):
            GPIO.output(int(beep_pin), GPIO.HIGH)
            time.sleep(float(beep_on))
            GPIO.output(int(beep_pin), GPIO.LOW)
            time.sleep(float(beep_off))
        try:
            GPIO.output(int(beep_pin), GPIO.LOW)
            GPIO.cleanup(int(beep_pin))
        except Exception:
            GPIO.cleanup()
        event["status"] = "executed"
    except Exception as exc:
        event["status"] = "error"
        event["error"] = repr(exc)
        event["traceback"] = traceback.format_exc()
    return event


def find_rgb_lib_paths():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.abspath(os.path.join(script_dir, os.pardir))
    candidates = [
        os.path.join(parent_dir, "new", "RGB_Lib.py"),
        os.path.join(parent_dir, "RGB_Lib.py"),
        os.path.join(os.getcwd(), "new", "RGB_Lib.py"),
        os.path.join(os.getcwd(), "RGB_Lib.py"),
        "/home/jetbot/Download/driver/RGB_Lib.py",
        "/home/jetbot/yahboom-jetbot/RGB_Lib.py",
    ]
    roots = [
        os.path.join(parent_dir, "new"),
        parent_dir,
        "/home/jetbot/Notebook",
        "/home/jetbot",
    ]
    paths = []
    for path in candidates:
        if os.path.exists(path):
            paths.append(path)
    for root in roots:
        if os.path.exists(root):
            paths.extend(glob.glob(os.path.join(root, "**", "RGB_Lib.py"), recursive=True))

    unique = []
    seen = set()
    for path in paths:
        norm = os.path.abspath(path)
        if norm not in seen:
            seen.add(norm)
            unique.append(path)
    return unique


def load_rgb_driver():
    errors = []
    for path in find_rgb_lib_paths():
        try:
            spec = importlib.util.spec_from_file_location("rgb_lib_dynamic", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            cls = getattr(module, "Programing_RGB")
            driver = cls()
            return driver, {
                "ok": True,
                "driver_path": path,
                "class_name": cls.__name__,
            }
        except Exception as exc:
            errors.append({"path": path, "error": repr(exc)})
    raise RuntimeError("Could not load RGB_Lib.py. Errors: {0}".format(errors))


def run_rgb_pattern(risk_level="warning", enable_rgb=True,
                    led_count=DEFAULT_RGB_LED_COUNT,
                    loops=DEFAULT_RGB_LOOPS,
                    step_delay=DEFAULT_RGB_STEP_DELAY,
                    blink_count=DEFAULT_RGB_BLINK_COUNT,
                    blink_on=DEFAULT_RGB_BLINK_ON,
                    blink_off=DEFAULT_RGB_BLINK_OFF,
                    off_at_end=True):
    level = normalize_risk_level(risk_level)
    color = RISK_COLORS.get(level, RISK_COLORS["warning"])
    event = {
        "time": now_string(),
        "type": "rgb",
        "risk_level": level,
        "color": color_to_hex(color),
        "led_count": int(led_count),
        "loops": int(loops),
        "blink_count": int(blink_count),
        "blink_on": blink_on,
        "blink_off": blink_off,
        "enable_rgb": bool(enable_rgb),
        "mode": "flow_then_full_strip_blink",
    }
    if not enable_rgb:
        event["status"] = "skipped"
        return event

    try:
        rgb, driver_info = load_rgb_driver()
        event["driver"] = driver_info
        for _ in range(int(loops)):
            for pos in range(int(led_count)):
                rgb.OFF_ALL_RGB()
                rgb.Set_An_RGB(pos, color[0], color[1], color[2])
                time.sleep(float(step_delay))
        for _ in range(int(blink_count)):
            rgb.Set_All_RGB(color[0], color[1], color[2])
            time.sleep(float(blink_on))
            rgb.OFF_ALL_RGB()
            time.sleep(float(blink_off))
        if off_at_end:
            rgb.OFF_ALL_RGB()
        else:
            rgb.Set_All_RGB(color[0], color[1], color[2])
        event["status"] = "executed"
        event["off_at_end"] = bool(off_at_end)
    except Exception as exc:
        event["status"] = "error"
        event["error"] = repr(exc)
        event["traceback"] = traceback.format_exc()
    return event


def write_text_report(report, path):
    lines = []
    lines.append("Inspection Feedback Tool")
    lines.append("Time: {0} -> {1}".format(report.get("started_at"), report.get("finished_at")))
    lines.append("Summary: {0}".format(report.get("summary")))
    lines.append("Risk level: {0}".format(report.get("risk_level")))
    lines.append("")
    lines.append("== Config ==")
    lines.append(json.dumps(report.get("config", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Loaded Search Report ==")
    lines.append(json.dumps(report.get("loaded_search_report", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Events ==")
    for event in report.get("events", []):
        lines.append(json.dumps(event, ensure_ascii=False))
    write_text(path, "\n".join(lines))


def summarize_report(report):
    lines = []
    lines.append("Inspection Feedback Tool")
    lines.append("Summary: {0}".format(report.get("summary")))
    lines.append("Risk level: {0}".format(report.get("risk_level")))
    for event in report.get("events", []):
        lines.append("{0}: {1}".format(event.get("type"), event.get("status")))
        if event.get("error"):
            lines.append("  error: {0}".format(event.get("error")))
    lines.append("JSON report: {0}".format(report.get("report_json")))
    lines.append("Text report: {0}".format(report.get("report_txt")))
    return "\n".join(lines)


def run_demo(output_dir=DEFAULT_OUTPUT_DIR,
             risk_level="warning",
             search_report_path=None,
             enable_buzzer=True,
             enable_rgb=True,
             beep_pin=DEFAULT_BEEP_PIN,
             beep_on=DEFAULT_BEEP_ON,
             beep_off=DEFAULT_BEEP_OFF,
             rgb_led_count=DEFAULT_RGB_LED_COUNT,
             rgb_loops=DEFAULT_RGB_LOOPS,
             rgb_step_delay=DEFAULT_RGB_STEP_DELAY,
             rgb_blink_count=DEFAULT_RGB_BLINK_COUNT,
             rgb_blink_on=DEFAULT_RGB_BLINK_ON,
             rgb_blink_off=DEFAULT_RGB_BLINK_OFF,
             rgb_off_at_end=True):
    ensure_dir(output_dir)
    loaded = load_search_risk_level(search_report_path) if search_report_path else {}
    if loaded.get("risk_level"):
        risk_level = loaded.get("risk_level")
    level = normalize_risk_level(risk_level)

    report = {
        "demo": "inspection_feedback_tool",
        "started_at": now_string(),
        "finished_at": None,
        "summary": "running",
        "risk_level": level,
        "loaded_search_report": loaded,
        "config": {
            "output_dir": output_dir,
            "risk_level": risk_level,
            "search_report_path": search_report_path,
            "enable_buzzer": enable_buzzer,
            "enable_rgb": enable_rgb,
            "beep_pin": beep_pin,
            "beep_on": beep_on,
            "beep_off": beep_off,
            "rgb_led_count": rgb_led_count,
            "rgb_loops": rgb_loops,
            "rgb_step_delay": rgb_step_delay,
            "rgb_blink_count": rgb_blink_count,
            "rgb_blink_on": rgb_blink_on,
            "rgb_blink_off": rgb_blink_off,
            "rgb_off_at_end": rgb_off_at_end,
        },
        "events": [],
    }

    report["events"].append(run_buzzer_pattern(
        risk_level=level,
        enable_buzzer=enable_buzzer,
        beep_pin=beep_pin,
        beep_on=beep_on,
        beep_off=beep_off,
    ))
    report["events"].append(run_rgb_pattern(
        risk_level=level,
        enable_rgb=enable_rgb,
        led_count=rgb_led_count,
        loops=rgb_loops,
        step_delay=rgb_step_delay,
        blink_count=rgb_blink_count,
        blink_on=rgb_blink_on,
        blink_off=rgb_blink_off,
        off_at_end=rgb_off_at_end,
    ))

    errors = [event for event in report["events"] if event.get("status") == "error"]
    if errors:
        report["summary"] = "Feedback completed with errors."
    else:
        report["summary"] = "Feedback completed."
    report["finished_at"] = now_string()

    json_path = os.path.join(output_dir, "inspection_feedback_report.json")
    text_path = os.path.join(output_dir, "inspection_feedback_report.txt")
    report["report_json"] = json_path
    report["report_txt"] = text_path
    write_json(json_path, report)
    write_text_report(report, text_path)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--risk-level", default="warning")
    parser.add_argument("--search-report-path", default=None)
    parser.add_argument("--no-buzzer", action="store_true")
    parser.add_argument("--no-rgb", action="store_true")
    parser.add_argument("--beep-pin", type=int, default=DEFAULT_BEEP_PIN)
    parser.add_argument("--beep-on", type=float, default=DEFAULT_BEEP_ON)
    parser.add_argument("--beep-off", type=float, default=DEFAULT_BEEP_OFF)
    parser.add_argument("--rgb-led-count", type=int, default=DEFAULT_RGB_LED_COUNT)
    parser.add_argument("--rgb-loops", type=int, default=DEFAULT_RGB_LOOPS)
    parser.add_argument("--rgb-step-delay", type=float, default=DEFAULT_RGB_STEP_DELAY)
    parser.add_argument("--rgb-blink-count", type=int, default=DEFAULT_RGB_BLINK_COUNT)
    parser.add_argument("--rgb-blink-on", type=float, default=DEFAULT_RGB_BLINK_ON)
    parser.add_argument("--rgb-blink-off", type=float, default=DEFAULT_RGB_BLINK_OFF)
    parser.add_argument("--rgb-keep-on", action="store_true")
    args = parser.parse_args(argv)

    report = run_demo(
        output_dir=args.output_dir,
        risk_level=args.risk_level,
        search_report_path=args.search_report_path,
        enable_buzzer=(not args.no_buzzer),
        enable_rgb=(not args.no_rgb),
        beep_pin=args.beep_pin,
        beep_on=args.beep_on,
        beep_off=args.beep_off,
        rgb_led_count=args.rgb_led_count,
        rgb_loops=args.rgb_loops,
        rgb_step_delay=args.rgb_step_delay,
        rgb_blink_count=args.rgb_blink_count,
        rgb_blink_on=args.rgb_blink_on,
        rgb_blink_off=args.rgb_blink_off,
        rgb_off_at_end=(not args.rgb_keep_on),
    )
    print(summarize_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
