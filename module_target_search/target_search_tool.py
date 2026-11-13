#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Target sign search tool for Yahboom Jetbot.

This module only does:
1. Move the camera gimbal through a small list of preset poses.
2. Capture one stable image at each candidate pose.
3. Ask StepFun vision model to choose whether/where the inspection sign appears.

It does not move the robot chassis and does not make final feedback actions.
"""

from __future__ import print_function

import argparse
import codecs
import json
import os
import re
import sys
import time
import traceback


PARENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

STEPFUN_DIR = os.path.join(PARENT_DIR, "module_stepfun_vision")
CAMERA_DIR = os.path.join(PARENT_DIR, "module_camera_capture")
for path in [STEPFUN_DIR, CAMERA_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)

from gimbal_scan_demo import (  # noqa: E402
    create_servo_driver,
    move_gimbal_smooth,
    prepare_servo_port,
)
from camera_capture_tool import (  # noqa: E402
    DEFAULT_CAMERA_HEIGHT,
    DEFAULT_CAMERA_WIDTH,
    capture_stable_image,
)
from qr_anchor_approach_demo import (  # noqa: E402
    DEFAULT_HOME_PAN,
    DEFAULT_HOME_TILT,
    ensure_dir,
    init_camera,
    release_camera,
)
from stepfun_vision_tool import (  # noqa: E402
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    StepFunVisionClient,
    extract_json,
    image_to_data_url,
)


CALIBRATED_HOME_PAN = 2048
CALIBRATED_HOME_TILT = 2868

DEFAULT_OUTPUT_DIR = "target_search_output"
DEFAULT_TARGET_TEXT = "工业工况巡检牌"
DEFAULT_SEARCH_PROFILE = "front_sign_wide"
DEFAULT_PAN_DELTA = 620
DEFAULT_TILT_UP_DELTA = 120
DEFAULT_TILT_DOWN_DELTA = 260
DEFAULT_STEP_SIZE = 20
DEFAULT_STEP_WAIT = 0.08
DEFAULT_GIMBAL_HOLD_SECONDS = 0.80
DEFAULT_CAPTURE_SAMPLES = 3
DEFAULT_CAPTURE_INTERVAL = 0.10
DEFAULT_PRE_CAPTURE_SETTLE = 0.30
DEFAULT_WARMUP_FRAMES = 1
DEFAULT_MAX_TOKENS = 4096


def now_string():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def write_json(path, data):
    with codecs.open(path, "w", "utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_text(path, text):
    with codecs.open(path, "w", "utf-8") as f:
        f.write(text)


def pose_table(home_pan=CALIBRATED_HOME_PAN,
               home_tilt=CALIBRATED_HOME_TILT,
               pan_delta=DEFAULT_PAN_DELTA,
               tilt_up_delta=DEFAULT_TILT_UP_DELTA,
               tilt_down_delta=DEFAULT_TILT_DOWN_DELTA,
               search_profile=DEFAULT_SEARCH_PROFILE):
    poses = {
        "center": (home_pan, home_tilt),
        # Pose names describe the target direction in the camera image/chassis
        # frame, not the raw servo sign. On the tested Yahboom gimbal, a larger
        # pan value looks toward the robot's left side.
        "left": (home_pan + pan_delta, home_tilt),
        "right": (home_pan - pan_delta, home_tilt),
        "up": (home_pan, home_tilt + tilt_up_delta),
        "down": (home_pan, home_tilt - tilt_down_delta),
    }
    if search_profile == "front_sign_wide":
        poses.update({
            "left_wide": (home_pan + int(pan_delta * 1.35), home_tilt),
            "right_wide": (home_pan - int(pan_delta * 1.35), home_tilt),
        })
    return poses


def scan_sequence(search_profile=DEFAULT_SEARCH_PROFILE):
    if search_profile == "front_sign_wide":
        return ["center", "left", "right", "left_wide", "right_wide", "down"]
    return ["center", "left", "right", "up", "down"]


def move_to_pose(driver, current_pan, current_tilt, pose_name, poses,
                 step_size=DEFAULT_STEP_SIZE,
                 step_wait=DEFAULT_STEP_WAIT,
                 hold_seconds=DEFAULT_GIMBAL_HOLD_SECONDS):
    pan, tilt = poses[pose_name]
    current_pan, current_tilt, sub_events = move_gimbal_smooth(
        driver,
        current_pan,
        current_tilt,
        pan,
        tilt,
        step_size=step_size,
        step_wait=step_wait,
    )
    if hold_seconds > 0:
        time.sleep(hold_seconds)
    return current_pan, current_tilt, {
        "time": now_string(),
        "pose": pose_name,
        "pan": current_pan,
        "tilt": current_tilt,
        "sub_event_count": len(sub_events),
        "hold_seconds": hold_seconds,
    }


def build_multiview_messages(target_text, candidate_images, allowed_poses):
    allowed_text = ", ".join(allowed_poses + ["none"])
    content = [
        {
            "type": "text",
            "text": (
                "任务：从多张云台候选图中寻找“{0}”。忽略只写有STOP/二维码的A01定位牌；"
                "优先寻找包含设备图片、状态文字、风险提示或处置建议的工业工况巡检牌。\n"
                "请充分进行多模态语义理解：逐图比较目标是否出现、画面是否完整、文字是否可读、"
                "设备状态是否正常、是否存在安全风险，并给出处置建议。\n"
                "风险分级标准：normal表示未发现明显异常，仅为正常设备或普通信息提示；"
                "warning表示存在轻微隐患、信息不确定、需要人工复核或持续观察；"
                "abnormal表示画面或文字中出现明确异常/危险信号，例如过热、高温读数、报警灯亮起、"
                "DANGER、OVERHEAT、漏油、裸露/散乱线缆、电气危险、停机/禁止靠近等，"
                "只要出现这些明确异常证据之一，就应优先判定为abnormal。\n"
                "必须只输出一个JSON对象，不要Markdown。best_pose只能是：{1}。\n"
                "JSON格式：{{\"target_found\":true/false,\"best_pose\":\"...\","
                "\"confidence\":0到1,\"visible_text\":\"读到的关键文字\","
                "\"pose_results\":{{\"pose\":\"该视角观察结论\"}},"
                "\"risk_level\":\"normal/warning/abnormal\","
                "\"inspection_summary\":\"巡检信息摘要\","
                "\"reason\":\"选择best_pose和风险等级的依据\","
                "\"next_action\":\"建议处置方案\"}}"
            ).format(target_text, allowed_text),
        }
    ]
    for item in candidate_images:
        content.append({
            "type": "text",
            "text": "候选图片 pose={0}".format(item["pose"]),
        })
        content.append({
            "type": "image_url",
            "image_url": {"url": image_to_data_url(item["path"])},
        })
    return [{"role": "user", "content": content}]


def analyze_candidates(candidate_images,
                       target_text=DEFAULT_TARGET_TEXT,
                       api_key=None,
                       key_file=None,
                       model=DEFAULT_MODEL,
                       endpoint=DEFAULT_ENDPOINT,
                       timeout=90,
                       reasoning_effort="low",
                       temperature=0.0,
                       max_tokens=DEFAULT_MAX_TOKENS):
    allowed_poses = [item["pose"] for item in candidate_images]
    client = StepFunVisionClient(
        api_key=api_key,
        key_file=key_file,
        model=model,
        endpoint=endpoint,
        timeout=timeout,
        reasoning_effort=reasoning_effort,
    )
    messages = build_multiview_messages(target_text, candidate_images, allowed_poses)
    text, raw = client.chat(messages, temperature=temperature, max_tokens=max_tokens)
    result = {
        "text": text,
        "parsed": {},
        "parse_ok": False,
        "parse_error": None,
        "raw_response": raw,
    }
    try:
        parsed = extract_json(text)
        if parsed.get("best_pose") not in allowed_poses + ["none"]:
            parsed["best_pose"] = "none"
            parsed["target_found"] = False
        result["parsed"] = parsed
        result["parse_ok"] = True
    except Exception as exc:
        result["parse_error"] = repr(exc)
        partial = salvage_partial_result(text, allowed_poses)
        if partial:
            result["parsed"] = partial
            result["partial_parse"] = True
    return result


def salvage_partial_result(text, allowed_poses):
    if not text:
        return None

    def find_bool(name):
        m = re.search(r'"{0}"\s*:\s*(true|false)'.format(name), text, re.I)
        if not m:
            return None
        return m.group(1).lower() == "true"

    def find_string(name):
        m = re.search(r'"{0}"\s*:\s*"([^"]*)"'.format(name), text)
        if not m:
            return None
        return m.group(1)

    def find_number(name):
        m = re.search(r'"{0}"\s*:\s*([0-9.]+)'.format(name), text)
        if not m:
            return None
        try:
            return float(m.group(1))
        except Exception:
            return None

    best_pose = find_string("best_pose")
    target_found = find_bool("target_found")
    if best_pose not in allowed_poses + ["none"]:
        return None
    if target_found is None and best_pose:
        target_found = best_pose != "none"

    return {
        "target_found": bool(target_found),
        "best_pose": best_pose or "none",
        "confidence": find_number("confidence"),
        "visible_text": find_string("visible_text") or "",
        "pose_results": {},
        "risk_level": find_string("risk_level") or "warning",
        "inspection_summary": find_string("inspection_summary") or "",
        "reason": find_string("reason") or "Recovered from partial VLM JSON.",
        "next_action": find_string("next_action") or "Use best_pose as tentative evidence.",
        "parse_note": "partial_json_recovered",
    }


def write_text_report(report, path):
    lines = []
    lines.append("Target Search Tool")
    lines.append("Time: {0} -> {1}".format(report.get("started_at"), report.get("finished_at")))
    lines.append("Summary: {0}".format(report.get("summary")))
    lines.append("")
    lines.append("== Config ==")
    lines.append(json.dumps(report.get("config", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Captures ==")
    for item in report.get("candidate_images", []):
        lines.append("{0}: {1}".format(item.get("pose"), item.get("path")))
    lines.append("")
    lines.append("== Vision Result ==")
    lines.append(json.dumps((report.get("vision") or {}).get("parsed", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Raw Text ==")
    lines.append((report.get("vision") or {}).get("text") or "")
    if report.get("error"):
        lines.append("")
        lines.append("== Error ==")
        lines.append(report.get("error"))
        lines.append("")
        lines.append("== Traceback ==")
        lines.append(report.get("traceback") or "")
    write_text(path, "\n".join(lines))


def summarize_report(report):
    vision = report.get("vision") or {}
    parsed = vision.get("parsed") or {}
    lines = []
    lines.append("Target Search Tool")
    lines.append("Summary: {0}".format(report.get("summary")))
    lines.append("Parse OK: {0}".format(vision.get("parse_ok")))
    lines.append("Partial parse: {0}".format(vision.get("partial_parse", False)))
    lines.append("Target found: {0}".format(parsed.get("target_found")))
    lines.append("Best pose: {0}".format(parsed.get("best_pose")))
    lines.append("Risk level: {0}".format(parsed.get("risk_level")))
    lines.append("JSON report: {0}".format(report.get("report_json")))
    lines.append("Text report: {0}".format(report.get("report_txt")))
    return "\n".join(lines)


def run_demo(output_dir=DEFAULT_OUTPUT_DIR,
             target_text=DEFAULT_TARGET_TEXT,
             api_key=None,
             key_file=None,
             model=DEFAULT_MODEL,
             endpoint=DEFAULT_ENDPOINT,
             timeout=90,
             reasoning_effort="low",
             home_pan=CALIBRATED_HOME_PAN,
             home_tilt=CALIBRATED_HOME_TILT,
             current_pan=None,
             current_tilt=None,
             pan_delta=DEFAULT_PAN_DELTA,
             tilt_up_delta=DEFAULT_TILT_UP_DELTA,
             tilt_down_delta=DEFAULT_TILT_DOWN_DELTA,
             search_profile=DEFAULT_SEARCH_PROFILE,
             step_size=DEFAULT_STEP_SIZE,
             step_wait=DEFAULT_STEP_WAIT,
             gimbal_hold_seconds=DEFAULT_GIMBAL_HOLD_SECONDS,
             camera_width=DEFAULT_CAMERA_WIDTH,
             camera_height=DEFAULT_CAMERA_HEIGHT,
             pre_capture_settle=DEFAULT_PRE_CAPTURE_SETTLE,
             capture_samples=DEFAULT_CAPTURE_SAMPLES,
             capture_interval=DEFAULT_CAPTURE_INTERVAL,
             warmup_frames=DEFAULT_WARMUP_FRAMES,
             max_tokens=DEFAULT_MAX_TOKENS,
             return_to_home=True):
    ensure_dir(output_dir)
    started_at = now_string()
    report = {
        "demo": "target_search_tool",
        "started_at": started_at,
        "finished_at": None,
        "summary": "running",
        "config": {
            "output_dir": output_dir,
            "target_text": target_text,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "home_pan": home_pan,
            "home_tilt": home_tilt,
            "pan_delta": pan_delta,
            "tilt_up_delta": tilt_up_delta,
            "tilt_down_delta": tilt_down_delta,
            "search_profile": search_profile,
            "step_size": step_size,
            "step_wait": step_wait,
            "gimbal_hold_seconds": gimbal_hold_seconds,
            "camera_width": camera_width,
            "camera_height": camera_height,
            "pre_capture_settle": pre_capture_settle,
            "capture_samples": capture_samples,
            "capture_interval": capture_interval,
            "warmup_frames": warmup_frames,
            "max_tokens": max_tokens,
            "return_to_home": return_to_home,
        },
        "servo_port": None,
        "driver": None,
        "camera_attempts": [],
        "events": [],
        "candidate_images": [],
        "vision": None,
        "final_pose": None,
        "error": None,
        "traceback": None,
    }

    camera = None
    try:
        report["servo_port"] = prepare_servo_port()
        driver, driver_info = create_servo_driver()
        report["driver"] = driver_info

        camera, attempts = init_camera(camera_width, camera_height, retry=True)
        report["camera_attempts"] = attempts

        poses = pose_table(
            home_pan=home_pan,
            home_tilt=home_tilt,
            pan_delta=pan_delta,
            tilt_up_delta=tilt_up_delta,
            tilt_down_delta=tilt_down_delta,
            search_profile=search_profile,
        )
        sequence = scan_sequence(search_profile)
        current_pan = int(current_pan if current_pan is not None else home_pan)
        current_tilt = int(current_tilt if current_tilt is not None else home_tilt)

        for pose_name in sequence:
            current_pan, current_tilt, event = move_to_pose(
                driver,
                current_pan,
                current_tilt,
                pose_name,
                poses,
                step_size=step_size,
                step_wait=step_wait,
                hold_seconds=gimbal_hold_seconds,
            )
            capture = capture_stable_image(
                camera,
                output_dir=output_dir,
                filename_prefix=pose_name,
                pre_capture_settle=pre_capture_settle,
                sample_count=capture_samples,
                sample_interval=capture_interval,
                warmup_frames=warmup_frames,
                save_all_samples=False,
            )
            event["capture"] = capture
            report["events"].append(event)
            report["candidate_images"].append({
                "pose": pose_name,
                "path": capture.get("image_path"),
                "selected_sample": capture.get("selected_sample"),
            })

        report["vision"] = analyze_candidates(
            report["candidate_images"],
            target_text=target_text,
            api_key=api_key,
            key_file=key_file,
            model=model,
            endpoint=endpoint,
            timeout=timeout,
            reasoning_effort=reasoning_effort,
            temperature=0.0,
            max_tokens=max_tokens,
        )

        parsed = report["vision"].get("parsed") or {}
        if return_to_home:
            current_pan, current_tilt, event = move_to_pose(
                driver,
                current_pan,
                current_tilt,
                "center",
                poses,
                step_size=step_size,
                step_wait=step_wait,
                hold_seconds=gimbal_hold_seconds,
            )
            event["type"] = "return_to_home"
            report["events"].append(event)

        report["final_pose"] = {
            "pan": current_pan,
            "tilt": current_tilt,
        }

        if parsed.get("target_found"):
            report["summary"] = "Target sign found."
        elif not report["vision"].get("parse_ok") and not report["vision"].get("partial_parse"):
            report["summary"] = "Search completed, but vision JSON parsing failed."
        else:
            report["summary"] = "Target sign not found."
    except Exception as exc:
        report["summary"] = "Error: {0}".format(repr(exc))
        report["error"] = repr(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        release_camera(camera)
        report["finished_at"] = now_string()

    json_path = os.path.join(output_dir, "target_search_report.json")
    text_path = os.path.join(output_dir, "target_search_report.txt")
    report["report_json"] = json_path
    report["report_txt"] = text_path
    write_json(json_path, report)
    write_text_report(report, text_path)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--target-text", default=DEFAULT_TARGET_TEXT)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--key-file", default=None)
    parser.add_argument("--model", default=os.environ.get("STEPFUN_VL_MODEL", DEFAULT_MODEL))
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--reasoning-effort", default="low")
    parser.add_argument("--home-pan", type=int, default=CALIBRATED_HOME_PAN)
    parser.add_argument("--home-tilt", type=int, default=CALIBRATED_HOME_TILT)
    parser.add_argument("--current-pan", type=int, default=None)
    parser.add_argument("--current-tilt", type=int, default=None)
    parser.add_argument("--pan-delta", type=int, default=DEFAULT_PAN_DELTA)
    parser.add_argument("--tilt-up-delta", type=int, default=DEFAULT_TILT_UP_DELTA)
    parser.add_argument("--tilt-down-delta", type=int, default=DEFAULT_TILT_DOWN_DELTA)
    parser.add_argument("--search-profile", default=DEFAULT_SEARCH_PROFILE,
                        choices=["front_sign", "front_sign_wide"])
    parser.add_argument("--step-size", type=int, default=DEFAULT_STEP_SIZE)
    parser.add_argument("--step-wait", type=float, default=DEFAULT_STEP_WAIT)
    parser.add_argument("--gimbal-hold-seconds", type=float, default=DEFAULT_GIMBAL_HOLD_SECONDS)
    parser.add_argument("--camera-width", type=int, default=DEFAULT_CAMERA_WIDTH)
    parser.add_argument("--camera-height", type=int, default=DEFAULT_CAMERA_HEIGHT)
    parser.add_argument("--pre-capture-settle", type=float, default=DEFAULT_PRE_CAPTURE_SETTLE)
    parser.add_argument("--capture-samples", type=int, default=DEFAULT_CAPTURE_SAMPLES)
    parser.add_argument("--capture-interval", type=float, default=DEFAULT_CAPTURE_INTERVAL)
    parser.add_argument("--warmup-frames", type=int, default=DEFAULT_WARMUP_FRAMES)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--no-return-home", action="store_true")
    args = parser.parse_args(argv)

    report = run_demo(
        output_dir=args.output_dir,
        target_text=args.target_text,
        api_key=args.api_key,
        key_file=args.key_file,
        model=args.model,
        endpoint=args.endpoint,
        timeout=args.timeout,
        reasoning_effort=args.reasoning_effort,
        home_pan=args.home_pan,
        home_tilt=args.home_tilt,
        current_pan=args.current_pan,
        current_tilt=args.current_tilt,
        pan_delta=args.pan_delta,
        tilt_up_delta=args.tilt_up_delta,
        tilt_down_delta=args.tilt_down_delta,
        search_profile=args.search_profile,
        step_size=args.step_size,
        step_wait=args.step_wait,
        gimbal_hold_seconds=args.gimbal_hold_seconds,
        camera_width=args.camera_width,
        camera_height=args.camera_height,
        pre_capture_settle=args.pre_capture_settle,
        capture_samples=args.capture_samples,
        capture_interval=args.capture_interval,
        warmup_frames=args.warmup_frames,
        max_tokens=args.max_tokens,
        return_to_home=(not args.no_return_home),
    )
    print(summarize_report(report))
    return 0 if not report.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
