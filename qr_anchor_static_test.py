#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Static QR anchor detection test for Yahboom Jetbot.

Use this before motion tests:
1. Put the robot at a known distance from the A01 stop-anchor sign.
2. Run this script.
3. Check whether OpenCV can decode the QR code and how wide the QR code is.

The script does not move the robot.
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
    DEFAULT_OUTPUT_DIR,
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
    parse_qr_payload,
    prepare_system,
    qr_center_from_points,
    qr_width_from_points,
    release_camera,
    write_json,
)


DEFAULT_STATIC_OUTPUT_DIR = "qr_anchor_static_output"


def normalize_points_for_original(points, scale):
    try:
        pts = points.reshape(-1, 2)
    except Exception:
        return None
    if len(pts) < 4:
        return None
    result = []
    for point in pts[:4]:
        result.append([float(point[0]) / float(scale), float(point[1]) / float(scale)])
    return result


def detect_with_variants(frame, detector):
    import cv2

    variants = []
    variants.append(("raw", frame, 1.0))

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    variants.append(("gray", gray, 1.0))

    for scale in [2.0, 3.0]:
        resized = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        variants.append(("gray_up_{0:g}x".format(scale), resized, scale))

    try:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        variants.append(("clahe", clahe, 1.0))
        for scale in [2.0, 3.0]:
            resized = cv2.resize(clahe, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            variants.append(("clahe_up_{0:g}x".format(scale), resized, scale))
    except Exception:
        pass

    try:
        binary = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            5,
        )
        variants.append(("adaptive_threshold", binary, 1.0))
        for scale in [2.0, 3.0]:
            resized = cv2.resize(binary, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
            variants.append(("adaptive_threshold_up_{0:g}x".format(scale), resized, scale))
    except Exception:
        pass

    results = []
    best = None
    for name, image, scale in variants:
        try:
            text, points, _ = detector.detectAndDecode(image)
        except Exception as exc:
            result = {
                "ok": False,
                "method": name,
                "error": repr(exc),
            }
            results.append(result)
            continue

        original_points = normalize_points_for_original(points, scale)
        width = qr_width_from_points(points)
        center = qr_center_from_points(points)
        if width is not None:
            width = float(width) / float(scale)
        if center is not None:
            center = [float(center[0]) / float(scale), float(center[1]) / float(scale)]

        result = {
            "ok": bool(text),
            "method": name,
            "decoded_text": text or "",
            "payload": parse_qr_payload(text),
            "points": original_points,
            "qr_width_px": width,
            "center": center,
            "scale": scale,
        }
        results.append(result)

        score = 0.0
        if result.get("ok"):
            score += 100000.0
        if result.get("qr_width_px"):
            score += float(result["qr_width_px"])

        best_score = -1.0
        if best is not None:
            if best.get("ok"):
                best_score += 100000.0
            if best.get("qr_width_px"):
                best_score += float(best["qr_width_px"])

        if best is None or score > best_score:
            best = result

    return best or {"ok": False}, results


def capture_static_samples(camera, output_dir, sample_count, interval_seconds,
                           stop_width_px, qr_real_width_mm, focal_px,
                           target_role, target_station):
    import cv2

    detector = cv2.QRCodeDetector()
    samples = []
    best_sample = None

    for index in range(int(sample_count)):
        if interval_seconds > 0:
            time.sleep(float(interval_seconds))

        frame = camera.value
        if frame is None:
            sample = {
                "index": index,
                "time": now_string(),
                "ok": False,
                "error": "camera.value is None",
            }
            samples.append(sample)
            continue

        best_detection, variant_results = detect_with_variants(frame, detector)
        target_ok = is_target_anchor(
            best_detection,
            target_role=target_role,
            target_station=target_station,
        )
        best_detection["target_ok"] = target_ok
        best_detection["distance_cm_estimate"] = estimate_distance_cm(
            best_detection.get("qr_width_px"),
            qr_real_width_mm,
            focal_px,
        )

        raw_path = os.path.join(output_dir, "sample_{:03d}.jpg".format(index))
        annotated_path = os.path.join(output_dir, "sample_{:03d}_annotated.jpg".format(index))
        cv2.imwrite(raw_path, frame)
        annotated = annotate_frame(frame, best_detection, stop_width_px, target_ok)
        cv2.imwrite(annotated_path, annotated)

        sample = {
            "index": index,
            "time": now_string(),
            "ok": bool(best_detection.get("ok")),
            "target_ok": target_ok,
            "best_detection": best_detection,
            "variant_results": variant_results,
            "image_path": raw_path,
            "annotated_image_path": annotated_path,
        }
        samples.append(sample)

        score = 0.0
        if sample.get("target_ok"):
            score += 1000000.0
        if sample.get("ok"):
            score += 100000.0
        width = best_detection.get("qr_width_px")
        if width:
            score += float(width)

        best_score = -1.0
        if best_sample is not None:
            if best_sample.get("target_ok"):
                best_score += 1000000.0
            if best_sample.get("ok"):
                best_score += 100000.0
            best_width = best_sample.get("best_detection", {}).get("qr_width_px")
            if best_width:
                best_score += float(best_width)

        if best_sample is None or score > best_score:
            best_sample = sample

    return samples, best_sample


def write_text_report(report, path):
    lines = []
    lines.append("QR Anchor Static Test")
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
    lines.append("== Best Sample ==")
    lines.append(json.dumps(report.get("best_sample", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Samples ==")
    for sample in report.get("samples", []):
        simple = {
            "index": sample.get("index"),
            "ok": sample.get("ok"),
            "target_ok": sample.get("target_ok"),
            "method": sample.get("best_detection", {}).get("method"),
            "payload": sample.get("best_detection", {}).get("payload"),
            "qr_width_px": sample.get("best_detection", {}).get("qr_width_px"),
            "image_path": sample.get("image_path"),
            "annotated_image_path": sample.get("annotated_image_path"),
        }
        lines.append(json.dumps(simple, ensure_ascii=False))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def summarize_report(report):
    lines = []
    lines.append("QR Anchor Static Test")
    lines.append("Summary: {0}".format(report.get("summary")))
    best = report.get("best_sample") or {}
    detection = best.get("best_detection") or {}
    lines.append("Best sample: {0}".format(best.get("index")))
    lines.append("Target OK: {0}".format(best.get("target_ok")))
    lines.append("Method: {0}".format(detection.get("method")))
    lines.append("Payload: {0}".format(json.dumps(detection.get("payload") or {}, ensure_ascii=False)))
    lines.append("QR width px: {0}".format(detection.get("qr_width_px")))
    if detection.get("distance_cm_estimate") is not None:
        lines.append("Estimated distance cm: {0:.1f}".format(detection["distance_cm_estimate"]))
    lines.append("JSON report: {0}".format(report.get("report_json")))
    lines.append("Text report: {0}".format(report.get("report_txt")))
    return "\n".join(lines)


def run_demo(output_dir=DEFAULT_STATIC_OUTPUT_DIR,
             distance_label="unknown",
             prepare=False,
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
             sample_count=8,
             interval_seconds=0.25):
    ensure_dir(output_dir)
    started_at = now_string()
    if stop_width_px is None:
        stop_width_px = float(camera_width) * float(stop_width_ratio)

    report = {
        "demo": "qr_anchor_static_test",
        "started_at": started_at,
        "finished_at": None,
        "summary": "running",
        "config": {
            "output_dir": output_dir,
            "distance_label": distance_label,
            "prepare": prepare,
            "init_gimbal": init_gimbal,
            "require_gimbal": require_gimbal,
            "home_pan": home_pan,
            "home_tilt": home_tilt,
            "gimbal_hold_seconds": gimbal_hold_seconds,
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
        "preparation": None,
        "gimbal": None,
        "camera_attempts": [],
        "samples": [],
        "best_sample": None,
    }

    camera = None
    try:
        if prepare:
            report["preparation"] = prepare_system()

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

        samples, best_sample = capture_static_samples(
            camera,
            output_dir,
            sample_count=sample_count,
            interval_seconds=interval_seconds,
            stop_width_px=stop_width_px,
            qr_real_width_mm=qr_real_width_mm,
            focal_px=focal_px,
            target_role=target_role,
            target_station=target_station,
        )
        report["samples"] = samples
        report["best_sample"] = best_sample

        if best_sample and best_sample.get("target_ok"):
            report["summary"] = "Target anchor decoded."
        elif best_sample and best_sample.get("ok"):
            report["summary"] = "A QR code was decoded, but it did not match the target anchor."
        else:
            report["summary"] = "No QR code decoded."

    except Exception as exc:
        report["summary"] = "Error: {0}".format(repr(exc))
        report["error"] = repr(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        release_camera(camera)
        report["finished_at"] = now_string()

    json_path = os.path.join(output_dir, "qr_anchor_static_report.json")
    text_path = os.path.join(output_dir, "qr_anchor_static_report.txt")
    report["report_json"] = json_path
    report["report_txt"] = text_path
    write_json(json_path, report)
    write_text_report(report, text_path)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=DEFAULT_STATIC_OUTPUT_DIR)
    parser.add_argument("--distance-label", default="unknown")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--skip-gimbal-init", action="store_true")
    parser.add_argument("--require-gimbal", action="store_true")
    parser.add_argument("--home-pan", type=int, default=DEFAULT_HOME_PAN)
    parser.add_argument("--home-tilt", type=int, default=DEFAULT_HOME_TILT)
    parser.add_argument("--gimbal-hold-seconds", type=float, default=1.0)
    parser.add_argument("--camera-width", type=int, default=DEFAULT_CAMERA_WIDTH)
    parser.add_argument("--camera-height", type=int, default=DEFAULT_CAMERA_HEIGHT)
    parser.add_argument("--stop-width-px", type=float, default=None)
    parser.add_argument("--stop-width-ratio", type=float, default=DEFAULT_STOP_WIDTH_RATIO)
    parser.add_argument("--qr-real-width-mm", type=float, default=DEFAULT_QR_REAL_WIDTH_MM)
    parser.add_argument("--focal-px", type=float, default=None)
    parser.add_argument("--target-role", default=DEFAULT_TARGET_ROLE)
    parser.add_argument("--target-station", default=DEFAULT_TARGET_STATION)
    parser.add_argument("--sample-count", type=int, default=8)
    parser.add_argument("--interval-seconds", type=float, default=0.25)
    args = parser.parse_args(argv)

    report = run_demo(
        output_dir=args.output_dir,
        distance_label=args.distance_label,
        prepare=args.prepare,
        init_gimbal=(not args.skip_gimbal_init),
        require_gimbal=args.require_gimbal,
        home_pan=args.home_pan,
        home_tilt=args.home_tilt,
        gimbal_hold_seconds=args.gimbal_hold_seconds,
        camera_width=args.camera_width,
        camera_height=args.camera_height,
        stop_width_px=args.stop_width_px,
        stop_width_ratio=args.stop_width_ratio,
        qr_real_width_mm=args.qr_real_width_mm,
        focal_px=args.focal_px,
        target_role=args.target_role,
        target_station=args.target_station,
        sample_count=args.sample_count,
        interval_seconds=args.interval_seconds,
    )
    print(summarize_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
