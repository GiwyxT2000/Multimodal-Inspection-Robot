#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Camera capture tool for Yahboom Jetbot.

This module only handles camera initialization and stable image capture.
It does not move the robot, decode QR codes, call any VLM, or control the
gimbal except for optional initialization to the calibrated front pose.
"""

from __future__ import print_function

import argparse
import json
import os
import sys
import time
import traceback


PARENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from qr_anchor_approach_demo import (  # noqa: E402
    DEFAULT_CAMERA_HEIGHT,
    DEFAULT_CAMERA_WIDTH,
    DEFAULT_HOME_PAN,
    DEFAULT_HOME_TILT,
    ensure_dir,
    frame_sharpness,
    init_camera,
    initialize_gimbal,
    now_string,
    release_camera,
    write_json,
)


DEFAULT_OUTPUT_DIR = "camera_capture_output"
DEFAULT_PRE_CAPTURE_SETTLE = 0.50
DEFAULT_SAMPLE_COUNT = 5
DEFAULT_SAMPLE_INTERVAL = 0.12
DEFAULT_WARMUP_FRAMES = 2


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def capture_stable_image(camera, output_dir=DEFAULT_OUTPUT_DIR,
                         filename_prefix="capture",
                         pre_capture_settle=DEFAULT_PRE_CAPTURE_SETTLE,
                         sample_count=DEFAULT_SAMPLE_COUNT,
                         sample_interval=DEFAULT_SAMPLE_INTERVAL,
                         warmup_frames=DEFAULT_WARMUP_FRAMES,
                         save_all_samples=False):
    import cv2

    ensure_dir(output_dir)

    if pre_capture_settle and float(pre_capture_settle) > 0:
        time.sleep(float(pre_capture_settle))

    for _ in range(max(0, int(warmup_frames))):
        _ = camera.value
        time.sleep(float(sample_interval))

    samples = []
    best_sample = None
    best_frame = None

    for index in range(max(1, int(sample_count))):
        time.sleep(float(sample_interval))
        frame = camera.value
        sharpness = frame_sharpness(frame)
        sample = {
            "index": index,
            "time": now_string(),
            "ok": frame is not None,
            "sharpness": sharpness,
            "image_path": None,
        }

        if frame is not None and save_all_samples:
            sample_path = os.path.join(output_dir, "{0}_sample_{1:03d}.jpg".format(filename_prefix, index))
            ok = cv2.imwrite(sample_path, frame)
            sample["image_path"] = sample_path if ok else None

        samples.append(sample)

        if frame is not None:
            current_score = float(sharpness or 0.0)
            best_score = float((best_sample or {}).get("sharpness") or -1.0)
            if best_sample is None or current_score > best_score:
                best_sample = dict(sample)
                best_frame = frame

    if best_frame is None:
        raise RuntimeError("Camera returned no frame during stable capture.")

    best_path = os.path.join(output_dir, "{0}_best.jpg".format(filename_prefix))
    ok = cv2.imwrite(best_path, best_frame)
    if not ok:
        raise RuntimeError("cv2.imwrite failed: {0}".format(best_path))

    best_sample["image_path"] = best_path
    return {
        "image_path": best_path,
        "selected_sample": best_sample,
        "samples": samples,
        "sample_count": len(samples),
    }


def write_text_report(report, path):
    lines = []
    lines.append("Camera Capture Tool")
    lines.append("Time: {0} -> {1}".format(report.get("started_at"), report.get("finished_at")))
    lines.append("Summary: {0}".format(report.get("summary")))
    lines.append("")
    lines.append("== Config ==")
    lines.append(json.dumps(report.get("config", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Gimbal ==")
    lines.append(json.dumps(report.get("gimbal", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Camera Attempts ==")
    lines.append(json.dumps(report.get("camera_attempts", []), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Capture ==")
    lines.append(json.dumps(report.get("capture", {}), ensure_ascii=False, indent=2))
    write_text(path, "\n".join(lines))


def summarize_report(report):
    capture = report.get("capture") or {}
    selected = capture.get("selected_sample") or {}
    lines = []
    lines.append("Camera Capture Tool")
    lines.append("Summary: {0}".format(report.get("summary")))
    lines.append("Image path: {0}".format(capture.get("image_path")))
    lines.append("Selected sample: {0}".format(selected.get("index")))
    lines.append("Sharpness: {0}".format(selected.get("sharpness")))
    lines.append("JSON report: {0}".format(report.get("report_json")))
    lines.append("Text report: {0}".format(report.get("report_txt")))
    return "\n".join(lines)


def run_demo(output_dir=DEFAULT_OUTPUT_DIR,
             filename_prefix="capture",
             init_gimbal=True,
             require_gimbal=False,
             home_pan=DEFAULT_HOME_PAN,
             home_tilt=DEFAULT_HOME_TILT,
             gimbal_hold_seconds=1.0,
             camera_width=DEFAULT_CAMERA_WIDTH,
             camera_height=DEFAULT_CAMERA_HEIGHT,
             pre_capture_settle=DEFAULT_PRE_CAPTURE_SETTLE,
             sample_count=DEFAULT_SAMPLE_COUNT,
             sample_interval=DEFAULT_SAMPLE_INTERVAL,
             warmup_frames=DEFAULT_WARMUP_FRAMES,
             save_all_samples=False):
    ensure_dir(output_dir)
    started_at = now_string()
    report = {
        "demo": "camera_capture_tool",
        "started_at": started_at,
        "finished_at": None,
        "summary": "running",
        "config": {
            "output_dir": output_dir,
            "filename_prefix": filename_prefix,
            "init_gimbal": init_gimbal,
            "require_gimbal": require_gimbal,
            "home_pan": home_pan,
            "home_tilt": home_tilt,
            "gimbal_hold_seconds": gimbal_hold_seconds,
            "camera_width": camera_width,
            "camera_height": camera_height,
            "pre_capture_settle": pre_capture_settle,
            "sample_count": sample_count,
            "sample_interval": sample_interval,
            "warmup_frames": warmup_frames,
            "save_all_samples": save_all_samples,
        },
        "gimbal": None,
        "camera_attempts": [],
        "capture": None,
        "error": None,
        "traceback": None,
    }

    camera = None
    try:
        if init_gimbal:
            report["gimbal"] = initialize_gimbal(
                home_pan=home_pan,
                home_tilt=home_tilt,
                hold_seconds=gimbal_hold_seconds,
            )
            if require_gimbal and not report["gimbal"].get("ok"):
                raise RuntimeError("Gimbal initialization failed: {0}".format(report["gimbal"]))

        camera, attempts = init_camera(camera_width, camera_height, retry=True)
        report["camera_attempts"] = attempts
        report["capture"] = capture_stable_image(
            camera,
            output_dir=output_dir,
            filename_prefix=filename_prefix,
            pre_capture_settle=pre_capture_settle,
            sample_count=sample_count,
            sample_interval=sample_interval,
            warmup_frames=warmup_frames,
            save_all_samples=save_all_samples,
        )
        report["summary"] = "Captured stable image."
    except Exception as exc:
        report["summary"] = "Error: {0}".format(repr(exc))
        report["error"] = repr(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        release_camera(camera)
        report["finished_at"] = now_string()

    json_path = os.path.join(output_dir, "camera_capture_report.json")
    text_path = os.path.join(output_dir, "camera_capture_report.txt")
    report["report_json"] = json_path
    report["report_txt"] = text_path
    write_json(json_path, report)
    write_text_report(report, text_path)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--filename-prefix", default="capture")
    parser.add_argument("--skip-gimbal-init", action="store_true")
    parser.add_argument("--require-gimbal", action="store_true")
    parser.add_argument("--home-pan", type=int, default=DEFAULT_HOME_PAN)
    parser.add_argument("--home-tilt", type=int, default=DEFAULT_HOME_TILT)
    parser.add_argument("--gimbal-hold-seconds", type=float, default=1.0)
    parser.add_argument("--camera-width", type=int, default=DEFAULT_CAMERA_WIDTH)
    parser.add_argument("--camera-height", type=int, default=DEFAULT_CAMERA_HEIGHT)
    parser.add_argument("--pre-capture-settle", type=float, default=DEFAULT_PRE_CAPTURE_SETTLE)
    parser.add_argument("--sample-count", type=int, default=DEFAULT_SAMPLE_COUNT)
    parser.add_argument("--sample-interval", type=float, default=DEFAULT_SAMPLE_INTERVAL)
    parser.add_argument("--warmup-frames", type=int, default=DEFAULT_WARMUP_FRAMES)
    parser.add_argument("--save-all-samples", action="store_true")
    args = parser.parse_args(argv)

    report = run_demo(
        output_dir=args.output_dir,
        filename_prefix=args.filename_prefix,
        init_gimbal=(not args.skip_gimbal_init),
        require_gimbal=args.require_gimbal,
        home_pan=args.home_pan,
        home_tilt=args.home_tilt,
        gimbal_hold_seconds=args.gimbal_hold_seconds,
        camera_width=args.camera_width,
        camera_height=args.camera_height,
        pre_capture_settle=args.pre_capture_settle,
        sample_count=args.sample_count,
        sample_interval=args.sample_interval,
        warmup_frames=args.warmup_frames,
        save_all_samples=args.save_all_samples,
    )
    print(summarize_report(report))
    return 0 if not report.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
