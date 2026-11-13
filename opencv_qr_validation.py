#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenCV-only QR validation for the A01 stop anchor.

This script does not move the robot and does not call any LLM. It only:
1. Initializes the gimbal and camera.
2. Captures several still frames.
3. Runs OpenCV QR detection/decoding variants.
4. Saves raw images, annotated images, and a JSON/TXT report.

Use it to measure at which distance OpenCV can reliably decode the QR code.
"""

from __future__ import print_function

import argparse
import json
import os
import time
import traceback

from qr_anchor_approach_demo import (
    DEFAULT_CAMERA_HEIGHT,
    DEFAULT_CAMERA_WIDTH,
    DEFAULT_HOME_PAN,
    DEFAULT_HOME_TILT,
    DEFAULT_QR_REAL_WIDTH_MM,
    DEFAULT_STOP_WIDTH_RATIO,
    DEFAULT_TARGET_ROLE,
    DEFAULT_TARGET_STATION,
    annotate_frame,
    ensure_dir,
    estimate_distance_cm,
    init_camera,
    initialize_gimbal,
    is_target_anchor,
    now_string,
    release_camera,
    write_json,
)
from qr_anchor_static_test import detect_with_variants


DEFAULT_OUTPUT_DIR = "opencv_qr_validation_output"


def write_text_report(report, path):
    lines = []
    lines.append("OpenCV QR Validation")
    lines.append("Time: {0} -> {1}".format(report.get("started_at"), report.get("finished_at")))
    lines.append("Summary: {0}".format(report.get("summary")))
    lines.append("")
    lines.append("== Config ==")
    lines.append(json.dumps(report.get("config", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Best Detection ==")
    lines.append(json.dumps(report.get("best_detection", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Samples ==")
    for sample in report.get("samples", []):
        lines.append(json.dumps({
            "index": sample.get("index"),
            "ok": sample.get("ok"),
            "target_ok": sample.get("target_ok"),
            "method": (sample.get("detection") or {}).get("method"),
            "qr_width_px": (sample.get("detection") or {}).get("qr_width_px"),
            "payload": (sample.get("detection") or {}).get("payload"),
            "image_path": sample.get("image_path"),
            "annotated_image_path": sample.get("annotated_image_path"),
        }, ensure_ascii=False))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def summarize_report(report):
    best = report.get("best_detection") or {}
    lines = []
    lines.append("OpenCV QR Validation")
    lines.append("Summary: {0}".format(report.get("summary")))
    lines.append("Decoded samples: {0}/{1}".format(
        report.get("decoded_count"),
        report.get("sample_count"),
    ))
    lines.append("Target samples: {0}/{1}".format(
        report.get("target_count"),
        report.get("sample_count"),
    ))
    lines.append("Best method: {0}".format(best.get("method")))
    lines.append("Best QR width px: {0}".format(best.get("qr_width_px")))
    lines.append("Best payload: {0}".format(json.dumps(best.get("payload") or {}, ensure_ascii=False)))
    if best.get("distance_cm_estimate") is not None:
        lines.append("Estimated distance cm: {0:.1f}".format(best["distance_cm_estimate"]))
    lines.append("JSON report: {0}".format(report.get("report_json")))
    lines.append("Text report: {0}".format(report.get("report_txt")))
    return "\n".join(lines)


def run_demo(output_dir=DEFAULT_OUTPUT_DIR,
             distance_label="unknown",
             init_gimbal=True,
             require_gimbal=False,
             home_pan=DEFAULT_HOME_PAN,
             home_tilt=DEFAULT_HOME_TILT,
             gimbal_hold_seconds=1.0,
             camera_width=DEFAULT_CAMERA_WIDTH,
             camera_height=DEFAULT_CAMERA_HEIGHT,
             stop_width_px=None,
             stop_width_ratio=DEFAULT_STOP_WIDTH_RATIO,
             qr_real_width_mm=DEFAULT_QR_REAL_WIDTH_MM,
             focal_px=None,
             target_role=DEFAULT_TARGET_ROLE,
             target_station=DEFAULT_TARGET_STATION,
             sample_count=12,
             interval_seconds=0.20):
    ensure_dir(output_dir)
    started_at = now_string()
    if stop_width_px is None:
        stop_width_px = float(camera_width) * float(stop_width_ratio)

    report = {
        "demo": "opencv_qr_validation",
        "started_at": started_at,
        "finished_at": None,
        "summary": "running",
        "config": {
            "output_dir": output_dir,
            "distance_label": distance_label,
            "init_gimbal": init_gimbal,
            "require_gimbal": require_gimbal,
            "home_pan": home_pan,
            "home_tilt": home_tilt,
            "camera_width": camera_width,
            "camera_height": camera_height,
            "stop_width_px": stop_width_px,
            "stop_width_ratio": stop_width_ratio,
            "qr_real_width_mm": qr_real_width_mm,
            "focal_px": focal_px,
            "target_role": target_role,
            "target_station": target_station,
            "sample_count": sample_count,
            "interval_seconds": interval_seconds,
        },
        "gimbal": None,
        "camera_attempts": [],
        "samples": [],
        "best_detection": None,
        "decoded_count": 0,
        "target_count": 0,
        "sample_count": int(sample_count),
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

        import cv2
        detector = cv2.QRCodeDetector()
        best_sample = None
        best_score = -1.0

        for index in range(int(sample_count)):
            if interval_seconds > 0:
                time.sleep(float(interval_seconds))
            frame = camera.value
            if frame is None:
                sample = {
                    "index": index,
                    "time": now_string(),
                    "ok": False,
                    "target_ok": False,
                    "error": "camera.value is None",
                }
                report["samples"].append(sample)
                continue

            detection, variants = detect_with_variants(frame, detector)
            target_ok = is_target_anchor(
                detection,
                target_role=target_role,
                target_station=target_station,
            )
            detection["target_ok"] = target_ok
            detection["distance_cm_estimate"] = estimate_distance_cm(
                detection.get("qr_width_px"),
                qr_real_width_mm,
                focal_px,
            )

            image_path = os.path.join(output_dir, "sample_{:03d}.jpg".format(index))
            annotated_path = os.path.join(output_dir, "sample_{:03d}_annotated.jpg".format(index))
            cv2.imwrite(image_path, frame)
            cv2.imwrite(annotated_path, annotate_frame(frame, detection, stop_width_px, target_ok))

            sample = {
                "index": index,
                "time": now_string(),
                "ok": bool(detection.get("ok")),
                "target_ok": target_ok,
                "detection": detection,
                "variant_results": variants,
                "image_path": image_path,
                "annotated_image_path": annotated_path,
            }
            report["samples"].append(sample)

            if sample["ok"]:
                report["decoded_count"] += 1
            if target_ok:
                report["target_count"] += 1

            score = 0.0
            if target_ok:
                score += 1000000.0
            if sample["ok"]:
                score += 100000.0
            if detection.get("qr_width_px"):
                score += float(detection["qr_width_px"])
            if score > best_score:
                best_score = score
                best_sample = sample

        report["best_detection"] = (best_sample or {}).get("detection") or {}
        if report["target_count"] > 0:
            report["summary"] = "Target QR decoded by OpenCV."
        elif report["decoded_count"] > 0:
            report["summary"] = "A QR code was decoded, but it did not match the target anchor."
        else:
            report["summary"] = "No QR code decoded by OpenCV."

    except Exception as exc:
        report["summary"] = "Error: {0}".format(repr(exc))
        report["error"] = repr(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        release_camera(camera)
        report["finished_at"] = now_string()

    json_path = os.path.join(output_dir, "opencv_qr_validation_report.json")
    text_path = os.path.join(output_dir, "opencv_qr_validation_report.txt")
    report["report_json"] = json_path
    report["report_txt"] = text_path
    write_json(json_path, report)
    write_text_report(report, text_path)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--distance-label", default="unknown")
    parser.add_argument("--skip-gimbal-init", action="store_true")
    parser.add_argument("--require-gimbal", action="store_true")
    parser.add_argument("--home-pan", type=int, default=DEFAULT_HOME_PAN)
    parser.add_argument("--home-tilt", type=int, default=DEFAULT_HOME_TILT)
    parser.add_argument("--camera-width", type=int, default=DEFAULT_CAMERA_WIDTH)
    parser.add_argument("--camera-height", type=int, default=DEFAULT_CAMERA_HEIGHT)
    parser.add_argument("--sample-count", type=int, default=12)
    parser.add_argument("--interval-seconds", type=float, default=0.20)
    parser.add_argument("--target-role", default=DEFAULT_TARGET_ROLE)
    parser.add_argument("--target-station", default=DEFAULT_TARGET_STATION)
    args = parser.parse_args(argv)

    report = run_demo(
        output_dir=args.output_dir,
        distance_label=args.distance_label,
        init_gimbal=(not args.skip_gimbal_init),
        require_gimbal=args.require_gimbal,
        home_pan=args.home_pan,
        home_tilt=args.home_tilt,
        camera_width=args.camera_width,
        camera_height=args.camera_height,
        sample_count=args.sample_count,
        interval_seconds=args.interval_seconds,
        target_role=args.target_role,
        target_station=args.target_station,
    )
    print(summarize_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
