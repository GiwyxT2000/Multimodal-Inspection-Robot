#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QR anchor approach demo for Yahboom Jetbot.

Goal:
1. Detect the A01 stop-anchor QR code with OpenCV.
2. Move forward in short straight steps while the QR code is too small.
3. Stop when the QR code width reaches the configured threshold.

Run on Jetbot:
    python3 qr_anchor_approach_demo.py

Safety:
- Clear the area in front of the robot before running.
- Keep one hand near the power switch.
- The robot only moves forward in short pulses, and stops after every pulse.
"""

from __future__ import print_function

import argparse
import json
import math
import os
import subprocess
import sys
import time
import traceback


DEFAULT_SUDO_PASSWORD = "yahboom"
DEFAULT_OUTPUT_DIR = "qr_anchor_approach_output"

DEFAULT_TARGET_ROLE = "stop_anchor"
DEFAULT_TARGET_STATION = "A01"
DEFAULT_QR_REAL_WIDTH_MM = 90.0

DEFAULT_CAMERA_WIDTH = 640
DEFAULT_CAMERA_HEIGHT = 480
DEFAULT_STOP_WIDTH_RATIO = 0.12

DEFAULT_HOME_PAN = 2048
DEFAULT_HOME_TILT = 2868

DEFAULT_STEP_SPEED = 0.55
DEFAULT_STEP_DURATION = 0.90
DEFAULT_FINE_STEP_SPEED = 0.42
DEFAULT_FINE_STEP_DURATION = 0.40
DEFAULT_FINE_WIDTH_RATIO = 0.55
DEFAULT_LATE_STEP_DURATION = 0.45
DEFAULT_SLOW_AFTER_STEPS = 3
DEFAULT_MICRO_STEP_SPEED = 0.32
DEFAULT_MICRO_STEP_DURATION = 0.16
DEFAULT_MICRO_WIDTH_RATIO = 0.82
DEFAULT_MAX_STEPS = 16
DEFAULT_MAX_MISSING_STEPS = 16
DEFAULT_MOTOR_KICK_SPEED = 0.75
DEFAULT_MOTOR_KICK_DURATION = 0.12
DEFAULT_POST_STOP_SETTLE = 0.90
DEFAULT_PRE_CAPTURE_SETTLE = 0.20
DEFAULT_CAPTURE_SAMPLE_INTERVAL = 0.12
DEFAULT_CAPTURE_WARMUP_FRAMES = 2
DEFAULT_FRAMES_PER_STEP = 5


def now_string():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run_cmd(cmd, timeout=15, stdin_text=None):
    try:
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE if stdin_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        stdout, stderr = p.communicate(input=stdin_text, timeout=timeout)
        return {
            "ok": p.returncode == 0,
            "returncode": p.returncode,
            "stdout": (stdout or "").strip(),
            "stderr": (stderr or "").strip(),
            "cmd": " ".join(cmd),
        }
    except Exception as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": repr(exc),
            "cmd": " ".join(cmd),
        }


def sudo_cmd(args, password=DEFAULT_SUDO_PASSWORD, timeout=20):
    return run_cmd(
        ["sudo", "-S", "-p", ""] + list(args),
        timeout=timeout,
        stdin_text=(password + "\n") if password else None,
    )


def prepare_system(password=DEFAULT_SUDO_PASSWORD, wait_seconds=4):
    steps = []
    steps.append({
        "name": "stop_jetbot_start",
        "result": sudo_cmd(["systemctl", "stop", "jetbot_start"], password=password),
    })
    steps.append({
        "name": "restart_nvargus_daemon",
        "result": sudo_cmd(["systemctl", "restart", "nvargus-daemon"], password=password),
    })
    time.sleep(wait_seconds)
    return {
        "ok": all(item["result"].get("ok") for item in steps),
        "steps": steps,
        "note": "Stopping jetbot_start is temporary and does not disable the service.",
    }


def initialize_gimbal(home_pan=DEFAULT_HOME_PAN, home_tilt=DEFAULT_HOME_TILT,
                      hold_seconds=1.0):
    try:
        from gimbal_scan_demo import (
            create_servo_driver,
            prepare_servo_port,
            set_double,
        )

        port = prepare_servo_port()
        driver, driver_info = create_servo_driver()
        home_event = set_double(driver, int(home_pan), int(home_tilt), wait=hold_seconds)
        return {
            "ok": bool(port.get("ok") and driver_info.get("ok")),
            "home_pan": int(home_pan),
            "home_tilt": int(home_tilt),
            "servo_port": port,
            "driver": driver_info,
            "home_event": home_event,
            "note": "Gimbal initialized to the calibrated front-facing pose.",
        }
    except Exception as exc:
        return {
            "ok": False,
            "home_pan": int(home_pan),
            "home_tilt": int(home_tilt),
            "error": repr(exc),
            "traceback": traceback.format_exc(),
        }


def release_camera(camera):
    if camera is not None:
        try:
            camera.stop()
        except Exception:
            pass
    try:
        from jetbot import Camera
        if hasattr(Camera, "_instance"):
            Camera._instance = None
    except Exception:
        pass


def reset_camera_runtime(password=DEFAULT_SUDO_PASSWORD, wait_seconds=5):
    release_camera(None)
    stop_service = sudo_cmd(["systemctl", "stop", "jetbot_start"], password=password, timeout=15)
    restart_camera = sudo_cmd(["systemctl", "restart", "nvargus-daemon"], password=password, timeout=20)
    time.sleep(wait_seconds)
    return {
        "stop_jetbot_start": stop_service,
        "restart_nvargus_daemon": restart_camera,
        "wait_seconds": wait_seconds,
        "note": "Stopping jetbot_start is temporary. It avoids official service camera conflicts.",
    }


def init_camera(width, height, retry=True, max_attempts=3,
                password=DEFAULT_SUDO_PASSWORD):
    from jetbot import Camera

    attempts = []
    camera = None
    total_attempts = max(1, int(max_attempts if retry else 1))

    for index in range(total_attempts):
        release_camera(camera)
        camera = None

        if index > 0:
            reset = reset_camera_runtime(password=password, wait_seconds=5)
            attempts.append({
                "name": "reset_camera_runtime",
                "attempt": index + 1,
                "ok": reset.get("restart_nvargus_daemon", {}).get("ok"),
                "detail": reset,
            })

        try:
            camera = Camera.instance(width=width, height=height)
            time.sleep(1.5)

            frame = None
            for _ in range(10):
                frame = camera.value
                if frame is not None:
                    break
                time.sleep(0.2)

            if frame is None:
                raise RuntimeError("camera.value is None after Camera.instance().")

            attempts.append({
                "name": "camera_init",
                "attempt": index + 1,
                "ok": True,
                "width": width,
                "height": height,
                "frame_shape": list(getattr(frame, "shape", [])),
            })
            return camera, attempts
        except Exception as exc:
            attempts.append({
                "name": "camera_init",
                "attempt": index + 1,
                "ok": False,
                "error": repr(exc),
            })
            release_camera(camera)
            camera = None

    raise RuntimeError("Could not initialize camera after {0} attempts: {1}".format(
        total_attempts,
        attempts,
    ))


def init_robot(enable_motion):
    from jetbot import Robot

    robot = Robot()
    robot.stop()
    if not enable_motion:
        robot.stop()
    return robot


def parse_qr_payload(text):
    if not text:
        return {}
    text = text.strip()
    normalized = text.upper().replace(" ", "").replace("-", "_")
    if normalized in ["A01_STOP", "A01STOP", "STOP_A01"]:
        return {
            "station": "A01",
            "role": "stop_anchor",
            "action": "approach_and_stop",
            "raw": text,
            "format": "short_code",
        }
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    return {"raw": text}


def point_distance(a, b):
    return math.sqrt((float(a[0]) - float(b[0])) ** 2 + (float(a[1]) - float(b[1])) ** 2)


def normalize_points(points):
    if points is None:
        return None
    try:
        pts = points.reshape(-1, 2)
    except Exception:
        return None
    if len(pts) < 4:
        return None
    return pts[:4]


def qr_width_from_points(points):
    pts = normalize_points(points)
    if pts is None:
        return None
    edges = [
        point_distance(pts[0], pts[1]),
        point_distance(pts[1], pts[2]),
        point_distance(pts[2], pts[3]),
        point_distance(pts[3], pts[0]),
    ]
    return sum(edges) / float(len(edges))


def qr_center_from_points(points):
    pts = normalize_points(points)
    if pts is None:
        return None
    x = sum(float(p[0]) for p in pts) / 4.0
    y = sum(float(p[1]) for p in pts) / 4.0
    return [x, y]


def decode_qr(frame, detector):
    try:
        result = detector.detectAndDecode(frame)
    except Exception as exc:
        return {
            "ok": False,
            "error": repr(exc),
        }

    if isinstance(result, tuple) and len(result) >= 3:
        text, points, _ = result[:3]
    else:
        return {
            "ok": False,
            "error": "Unexpected detectAndDecode result.",
        }

    width = qr_width_from_points(points)
    center = qr_center_from_points(points)
    payload = parse_qr_payload(text)
    return {
        "ok": bool(text),
        "decoded_text": text or "",
        "payload": payload,
        "points": normalize_points(points).tolist() if normalize_points(points) is not None else None,
        "qr_width_px": width,
        "center": center,
    }


def annotate_frame(frame, detection, stop_width_px, target_ok):
    import cv2

    output = frame.copy()
    points = detection.get("points")
    if points:
        pts = []
        for x, y in points:
            pts.append((int(round(x)), int(round(y))))
        for i in range(4):
            color = (0, 255, 0) if target_ok else (0, 180, 255)
            cv2.line(output, pts[i], pts[(i + 1) % 4], color, 2)

    width = detection.get("qr_width_px")
    role = detection.get("payload", {}).get("role", "")
    station = detection.get("payload", {}).get("station", "")
    text = "role={} station={} width={:.1f}/{:.1f}".format(
        role,
        station,
        float(width or 0),
        float(stop_width_px),
    )
    cv2.putText(output, text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    return output


def estimate_distance_cm(qr_width_px, qr_real_width_mm, focal_px):
    if not qr_width_px or not focal_px:
        return None
    distance_mm = float(focal_px) * float(qr_real_width_mm) / float(qr_width_px)
    return distance_mm / 10.0


def frame_sharpness(frame):
    if frame is None:
        return None
    try:
        import cv2

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except Exception:
        return None


def is_target_anchor(detection, target_role, target_station=None):
    payload = detection.get("payload") or {}
    role_ok = payload.get("role") == target_role
    station_ok = True
    if target_station:
        station_ok = payload.get("station") == target_station
    return bool(role_ok and station_ok)


def detection_score(detection):
    if not detection:
        return -1.0
    ok_bonus = 1000000.0 if detection.get("ok") else 0.0
    width_score = float(detection.get("qr_width_px") or 0.0) * 1000.0
    sharp_score = float(detection.get("sharpness") or 0.0)
    return ok_bonus + width_score + sharp_score


def best_detection_from_frames(camera, detector, frame_count=DEFAULT_FRAMES_PER_STEP,
                               settle_seconds=DEFAULT_CAPTURE_SAMPLE_INTERVAL,
                               pre_capture_settle=DEFAULT_PRE_CAPTURE_SETTLE,
                               warmup_frames=DEFAULT_CAPTURE_WARMUP_FRAMES):
    best = None
    best_frame = None
    all_detections = []
    best_index = None

    if pre_capture_settle and float(pre_capture_settle) > 0:
        time.sleep(float(pre_capture_settle))

    for _ in range(max(0, int(warmup_frames))):
        _ = camera.value
        time.sleep(float(settle_seconds))

    for index in range(max(1, int(frame_count))):
        time.sleep(settle_seconds)
        frame = camera.value
        if frame is None:
            detection = {"ok": False, "error": "camera.value is None"}
        else:
            detection = decode_qr(frame, detector)
            detection["sharpness"] = frame_sharpness(frame)
        detection["sample_index"] = index
        all_detections.append(detection)

        if best is None or detection_score(detection) > detection_score(best):
            best = detection
            best_frame = frame
            best_index = index

    if best is not None:
        best["selected_sample_index"] = best_index
    return best or {"ok": False}, best_frame, all_detections


def camera_preflight(camera, detector, output_dir, stop_width_px,
                     target_role, target_station, frame_count=5,
                     pre_capture_settle=0.50,
                     capture_sample_interval=DEFAULT_CAPTURE_SAMPLE_INTERVAL,
                     capture_warmup_frames=DEFAULT_CAPTURE_WARMUP_FRAMES):
    import cv2

    detection, frame, all_detections = best_detection_from_frames(
        camera,
        detector,
        frame_count=frame_count,
        settle_seconds=capture_sample_interval,
        pre_capture_settle=pre_capture_settle,
        warmup_frames=capture_warmup_frames,
    )
    target_ok = is_target_anchor(
        detection,
        target_role=target_role,
        target_station=target_station,
    )
    detection["target_ok"] = target_ok

    result = {
        "time": now_string(),
        "ok": frame is not None,
        "target_ok": target_ok,
        "detection": detection,
        "all_detections": all_detections,
    }

    if frame is not None:
        raw_path = os.path.join(output_dir, "camera_init_frame.jpg")
        annotated_path = os.path.join(output_dir, "camera_init_frame_annotated.jpg")
        cv2.imwrite(raw_path, frame)
        annotated = annotate_frame(frame, detection, stop_width_px, target_ok)
        cv2.imwrite(annotated_path, annotated)
        result["image_path"] = raw_path
        result["annotated_image_path"] = annotated_path

    return result


def move_forward_pulse(robot, enable_motion, speed, duration,
                       kick_speed=DEFAULT_MOTOR_KICK_SPEED,
                       kick_duration=DEFAULT_MOTOR_KICK_DURATION,
                       post_stop_settle=DEFAULT_POST_STOP_SETTLE):
    event = {
        "time": now_string(),
        "action": "forward_pulse",
        "enable_motion": bool(enable_motion),
        "speed": speed,
        "duration": duration,
        "kick_speed": kick_speed,
        "kick_duration": kick_duration,
        "post_stop_settle": post_stop_settle,
    }
    if not enable_motion:
        event["status"] = "dry_run"
        return event
    try:
        if kick_duration and float(kick_duration) > 0:
            robot.forward(float(kick_speed))
            time.sleep(float(kick_duration))
        robot.forward(speed)
        time.sleep(duration)
        robot.stop()
        if post_stop_settle and float(post_stop_settle) > 0:
            time.sleep(float(post_stop_settle))
        event["status"] = "executed"
    except Exception as exc:
        try:
            robot.stop()
        except Exception:
            pass
        event["status"] = "error"
        event["error"] = repr(exc)
        raise
    return event


def move_backward_pulse(robot, enable_motion, speed, duration,
                        post_stop_settle=DEFAULT_POST_STOP_SETTLE):
    event = {
        "time": now_string(),
        "action": "backward_pulse",
        "enable_motion": bool(enable_motion),
        "speed": speed,
        "duration": duration,
        "post_stop_settle": post_stop_settle,
    }
    if not enable_motion:
        event["status"] = "dry_run"
        return event
    try:
        robot.backward(float(speed))
        time.sleep(float(duration))
        robot.stop()
        if post_stop_settle and float(post_stop_settle) > 0:
            time.sleep(float(post_stop_settle))
        event["status"] = "executed"
    except Exception as exc:
        try:
            robot.stop()
        except Exception:
            pass
        event["status"] = "error"
        event["error"] = repr(exc)
        raise
    return event


def choose_motion_profile(detection, target_ok, stop_width_px,
                          coarse_speed, coarse_duration,
                          fine_speed, fine_duration,
                          fine_width_ratio,
                          step_index=0,
                          slow_after_steps=DEFAULT_SLOW_AFTER_STEPS,
                          late_step_duration=DEFAULT_LATE_STEP_DURATION,
                          micro_speed=DEFAULT_MICRO_STEP_SPEED,
                          micro_duration=DEFAULT_MICRO_STEP_DURATION,
                          micro_width_ratio=DEFAULT_MICRO_WIDTH_RATIO):
    qr_width = detection.get("qr_width_px") if detection else None
    fine_trigger_width = float(stop_width_px) * float(fine_width_ratio)
    micro_trigger_width = float(stop_width_px) * float(micro_width_ratio)
    use_fine = bool(target_ok and qr_width is not None and float(qr_width) >= fine_trigger_width)
    use_micro = bool(target_ok and qr_width is not None and float(qr_width) >= micro_trigger_width)

    if use_micro:
        return {
            "profile": "micro",
            "speed": float(micro_speed),
            "duration": float(micro_duration),
            "fine_trigger_width_px": fine_trigger_width,
            "micro_trigger_width_px": micro_trigger_width,
        }

    if use_fine:
        return {
            "profile": "fine",
            "speed": float(fine_speed),
            "duration": float(fine_duration),
            "fine_trigger_width_px": fine_trigger_width,
            "micro_trigger_width_px": micro_trigger_width,
        }

    duration = float(coarse_duration)
    profile = "coarse"
    if int(step_index) >= int(slow_after_steps):
        duration = min(duration, float(late_step_duration))
        profile = "late_coarse"

    return {
        "profile": profile,
        "speed": float(coarse_speed),
        "duration": duration,
        "fine_trigger_width_px": fine_trigger_width,
        "micro_trigger_width_px": micro_trigger_width,
    }


def write_text_report(report, path):
    lines = []
    lines.append("QR Anchor Approach Demo")
    lines.append("Time: {0} -> {1}".format(report.get("started_at"), report.get("finished_at")))
    lines.append("Summary: {0}".format(report.get("summary")))
    lines.append("")
    lines.append("== Config ==")
    lines.append(json.dumps(report.get("config", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Preparation ==")
    lines.append(json.dumps(report.get("preparation", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Gimbal ==")
    lines.append(json.dumps(report.get("gimbal", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Camera Preflight ==")
    lines.append(json.dumps(report.get("camera_preflight", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Events ==")
    for event in report.get("events", []):
        lines.append(json.dumps(event, ensure_ascii=False))
    lines.append("")
    lines.append("== Final Detection ==")
    lines.append(json.dumps(report.get("final_detection", {}), ensure_ascii=False, indent=2))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def summarize_report(report):
    lines = []
    lines.append("QR Anchor Approach Demo")
    lines.append("Summary: {0}".format(report.get("summary")))
    lines.append("Stop reason: {0}".format(report.get("stop_reason")))
    lines.append("Moved steps: {0}".format(report.get("moved_steps")))
    final_detection = report.get("final_detection") or {}
    if final_detection:
        payload = final_detection.get("payload") or {}
        lines.append("Final payload: {0}".format(json.dumps(payload, ensure_ascii=False)))
        lines.append("Final QR width: {0}".format(final_detection.get("qr_width_px")))
        if final_detection.get("distance_cm_estimate") is not None:
            lines.append("Estimated distance cm: {0:.1f}".format(final_detection["distance_cm_estimate"]))
    if report.get("report_json"):
        lines.append("JSON report: {0}".format(report.get("report_json")))
    if report.get("report_txt"):
        lines.append("Text report: {0}".format(report.get("report_txt")))
    return "\n".join(lines)


def run_demo(
    output_dir=DEFAULT_OUTPUT_DIR,
    prepare=True,
    init_gimbal=True,
    require_gimbal=True,
    home_pan=DEFAULT_HOME_PAN,
    home_tilt=DEFAULT_HOME_TILT,
    gimbal_hold_seconds=1.0,
    enable_motion=True,
    camera_width=DEFAULT_CAMERA_WIDTH,
    camera_height=DEFAULT_CAMERA_HEIGHT,
    target_role=DEFAULT_TARGET_ROLE,
    target_station=DEFAULT_TARGET_STATION,
    stop_width_px=None,
    stop_width_ratio=DEFAULT_STOP_WIDTH_RATIO,
    qr_real_width_mm=DEFAULT_QR_REAL_WIDTH_MM,
    focal_px=None,
    step_speed=DEFAULT_STEP_SPEED,
    step_duration=DEFAULT_STEP_DURATION,
    fine_step_speed=DEFAULT_FINE_STEP_SPEED,
    fine_step_duration=DEFAULT_FINE_STEP_DURATION,
    fine_width_ratio=DEFAULT_FINE_WIDTH_RATIO,
    late_step_duration=DEFAULT_LATE_STEP_DURATION,
    slow_after_steps=DEFAULT_SLOW_AFTER_STEPS,
    micro_step_speed=DEFAULT_MICRO_STEP_SPEED,
    micro_step_duration=DEFAULT_MICRO_STEP_DURATION,
    micro_width_ratio=DEFAULT_MICRO_WIDTH_RATIO,
    motor_kick_speed=DEFAULT_MOTOR_KICK_SPEED,
    motor_kick_duration=DEFAULT_MOTOR_KICK_DURATION,
    enable_backoff=False,
    backoff_width_ratio=1.35,
    backoff_speed=0.30,
    backoff_duration=0.18,
    max_steps=DEFAULT_MAX_STEPS,
    max_missing_steps=DEFAULT_MAX_MISSING_STEPS,
    frames_per_step=DEFAULT_FRAMES_PER_STEP,
    post_stop_settle=DEFAULT_POST_STOP_SETTLE,
    pre_capture_settle=DEFAULT_PRE_CAPTURE_SETTLE,
    capture_sample_interval=DEFAULT_CAPTURE_SAMPLE_INTERVAL,
    capture_warmup_frames=DEFAULT_CAPTURE_WARMUP_FRAMES,
    save_frames=True,
):
    ensure_dir(output_dir)
    started_at = now_string()

    if stop_width_px is None:
        stop_width_px = float(camera_width) * float(stop_width_ratio)

    report = {
        "demo": "qr_anchor_approach_demo",
        "started_at": started_at,
        "finished_at": None,
        "summary": "running",
        "stop_reason": None,
        "moved_steps": 0,
        "missing_steps": 0,
        "config": {
            "output_dir": output_dir,
            "prepare": prepare,
            "init_gimbal": init_gimbal,
            "require_gimbal": require_gimbal,
            "home_pan": home_pan,
            "home_tilt": home_tilt,
            "gimbal_hold_seconds": gimbal_hold_seconds,
            "enable_motion": enable_motion,
            "camera_width": camera_width,
            "camera_height": camera_height,
            "target_role": target_role,
            "target_station": target_station,
            "stop_width_px": stop_width_px,
            "stop_width_ratio": stop_width_ratio,
            "qr_real_width_mm": qr_real_width_mm,
            "focal_px": focal_px,
            "step_speed": step_speed,
            "step_duration": step_duration,
            "fine_step_speed": fine_step_speed,
            "fine_step_duration": fine_step_duration,
            "fine_width_ratio": fine_width_ratio,
            "late_step_duration": late_step_duration,
            "slow_after_steps": slow_after_steps,
            "micro_step_speed": micro_step_speed,
            "micro_step_duration": micro_step_duration,
            "micro_width_ratio": micro_width_ratio,
            "motor_kick_speed": motor_kick_speed,
            "motor_kick_duration": motor_kick_duration,
            "enable_backoff": enable_backoff,
            "backoff_width_ratio": backoff_width_ratio,
            "backoff_speed": backoff_speed,
            "backoff_duration": backoff_duration,
            "max_steps": max_steps,
            "max_missing_steps": max_missing_steps,
            "frames_per_step": frames_per_step,
            "post_stop_settle": post_stop_settle,
            "pre_capture_settle": pre_capture_settle,
            "capture_sample_interval": capture_sample_interval,
            "capture_warmup_frames": capture_warmup_frames,
            "save_frames": save_frames,
        },
        "preparation": None,
        "gimbal": None,
        "camera_preflight": None,
        "camera_attempts": [],
        "events": [],
        "final_detection": None,
    }

    robot = None
    camera = None

    try:
        import cv2

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

        detector = cv2.QRCodeDetector()
        robot = init_robot(enable_motion=enable_motion)
        camera, attempts = init_camera(camera_width, camera_height, retry=True)
        report["camera_attempts"] = attempts
        report["camera_preflight"] = camera_preflight(
            camera,
            detector,
            output_dir,
            stop_width_px,
            target_role=target_role,
            target_station=target_station,
            frame_count=max(3, int(frames_per_step)),
            pre_capture_settle=max(float(pre_capture_settle), 0.50),
            capture_sample_interval=capture_sample_interval,
            capture_warmup_frames=capture_warmup_frames,
        )

        for step_index in range(int(max_steps) + 1):
            detection, frame, all_detections = best_detection_from_frames(
                camera,
                detector,
                frame_count=frames_per_step,
                settle_seconds=capture_sample_interval,
                pre_capture_settle=pre_capture_settle,
                warmup_frames=capture_warmup_frames,
            )
            target_ok = is_target_anchor(
                detection,
                target_role=target_role,
                target_station=target_station,
            )

            distance_cm = estimate_distance_cm(
                detection.get("qr_width_px"),
                qr_real_width_mm,
                focal_px,
            )
            detection["distance_cm_estimate"] = distance_cm
            detection["target_ok"] = target_ok

            event = {
                "time": now_string(),
                "step_index": step_index,
                "type": "observe",
                "target_ok": target_ok,
                "detection": detection,
                "all_detections": all_detections,
            }

            if save_frames and frame is not None:
                raw_path = os.path.join(output_dir, "step_{:03d}.jpg".format(step_index))
                annotated_path = os.path.join(output_dir, "step_{:03d}_annotated.jpg".format(step_index))
                cv2.imwrite(raw_path, frame)
                annotated = annotate_frame(frame, detection, stop_width_px, target_ok)
                cv2.imwrite(annotated_path, annotated)
                event["image_path"] = raw_path
                event["annotated_image_path"] = annotated_path

            report["events"].append(event)
            report["final_detection"] = detection

            qr_width = detection.get("qr_width_px")
            if target_ok and qr_width is not None and float(qr_width) >= float(stop_width_px):
                report["stop_reason"] = "target_anchor_reached"
                report["summary"] = "Reached the QR stop-anchor width threshold."
                if bool(enable_backoff) and float(qr_width) >= float(stop_width_px) * float(backoff_width_ratio):
                    backoff_event = move_backward_pulse(
                        robot,
                        enable_motion=enable_motion,
                        speed=backoff_speed,
                        duration=backoff_duration,
                        post_stop_settle=post_stop_settle,
                    )
                    backoff_event["reason"] = "qr_width_exceeded_backoff_threshold"
                    backoff_event["backoff_threshold_px"] = float(stop_width_px) * float(backoff_width_ratio)
                    report["events"].append(backoff_event)
                    report["summary"] = "Reached the QR stop-anchor width threshold and backed off slightly."
                break

            if step_index >= int(max_steps):
                report["stop_reason"] = "max_steps_reached"
                report["summary"] = "Stopped because max_steps was reached before the stop threshold."
                break

            if not target_ok:
                report["missing_steps"] += 1
                if report["missing_steps"] > int(max_missing_steps):
                    report["stop_reason"] = "max_missing_steps_reached"
                    report["summary"] = "Stopped because the target anchor was missing too many times."
                    break
            else:
                report["missing_steps"] = 0

            motion_profile = choose_motion_profile(
                detection,
                target_ok,
                stop_width_px,
                coarse_speed=step_speed,
                coarse_duration=step_duration,
                fine_speed=fine_step_speed,
                fine_duration=fine_step_duration,
                fine_width_ratio=fine_width_ratio,
                step_index=report["moved_steps"],
                slow_after_steps=slow_after_steps,
                late_step_duration=late_step_duration,
                micro_speed=micro_step_speed,
                micro_duration=micro_step_duration,
                micro_width_ratio=micro_width_ratio,
            )
            move_event = move_forward_pulse(
                robot,
                enable_motion=enable_motion,
                speed=motion_profile["speed"],
                duration=motion_profile["duration"],
                kick_speed=motor_kick_speed,
                kick_duration=motor_kick_duration,
                post_stop_settle=post_stop_settle,
            )
            move_event["profile"] = motion_profile["profile"]
            move_event["fine_trigger_width_px"] = motion_profile["fine_trigger_width_px"]
            report["events"].append(move_event)
            if enable_motion:
                report["moved_steps"] += 1

        try:
            robot.stop()
        except Exception:
            pass

    except Exception as exc:
        report["summary"] = "Error: {0}".format(repr(exc))
        report["stop_reason"] = "error"
        report["error"] = repr(exc)
        report["traceback"] = traceback.format_exc()
        try:
            if robot is not None:
                robot.stop()
        except Exception:
            pass
    finally:
        release_camera(camera)
        report["finished_at"] = now_string()

    json_path = os.path.join(output_dir, "qr_anchor_approach_report.json")
    text_path = os.path.join(output_dir, "qr_anchor_approach_report.txt")
    report["report_json"] = json_path
    report["report_txt"] = text_path
    write_json(json_path, report)
    write_text_report(report, text_path)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--skip-prepare", action="store_true")
    parser.add_argument("--skip-gimbal-init", action="store_true")
    parser.add_argument("--allow-gimbal-failure", action="store_true")
    parser.add_argument("--home-pan", type=int, default=DEFAULT_HOME_PAN)
    parser.add_argument("--home-tilt", type=int, default=DEFAULT_HOME_TILT)
    parser.add_argument("--gimbal-hold-seconds", type=float, default=1.0)
    parser.add_argument("--no-motion", action="store_true")
    parser.add_argument("--camera-width", type=int, default=DEFAULT_CAMERA_WIDTH)
    parser.add_argument("--camera-height", type=int, default=DEFAULT_CAMERA_HEIGHT)
    parser.add_argument("--target-role", default=DEFAULT_TARGET_ROLE)
    parser.add_argument("--target-station", default=DEFAULT_TARGET_STATION)
    parser.add_argument("--stop-width-px", type=float, default=None)
    parser.add_argument("--stop-width-ratio", type=float, default=DEFAULT_STOP_WIDTH_RATIO)
    parser.add_argument("--qr-real-width-mm", type=float, default=DEFAULT_QR_REAL_WIDTH_MM)
    parser.add_argument("--focal-px", type=float, default=None)
    parser.add_argument("--step-speed", type=float, default=DEFAULT_STEP_SPEED)
    parser.add_argument("--step-duration", type=float, default=DEFAULT_STEP_DURATION)
    parser.add_argument("--fine-step-speed", type=float, default=DEFAULT_FINE_STEP_SPEED)
    parser.add_argument("--fine-step-duration", type=float, default=DEFAULT_FINE_STEP_DURATION)
    parser.add_argument("--fine-width-ratio", type=float, default=DEFAULT_FINE_WIDTH_RATIO)
    parser.add_argument("--late-step-duration", type=float, default=DEFAULT_LATE_STEP_DURATION)
    parser.add_argument("--slow-after-steps", type=int, default=DEFAULT_SLOW_AFTER_STEPS)
    parser.add_argument("--micro-step-speed", type=float, default=DEFAULT_MICRO_STEP_SPEED)
    parser.add_argument("--micro-step-duration", type=float, default=DEFAULT_MICRO_STEP_DURATION)
    parser.add_argument("--micro-width-ratio", type=float, default=DEFAULT_MICRO_WIDTH_RATIO)
    parser.add_argument("--motor-kick-speed", type=float, default=DEFAULT_MOTOR_KICK_SPEED)
    parser.add_argument("--motor-kick-duration", type=float, default=DEFAULT_MOTOR_KICK_DURATION)
    parser.add_argument("--enable-backoff", action="store_true")
    parser.add_argument("--backoff-width-ratio", type=float, default=1.35)
    parser.add_argument("--backoff-speed", type=float, default=0.30)
    parser.add_argument("--backoff-duration", type=float, default=0.18)
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    parser.add_argument("--max-missing-steps", type=int, default=DEFAULT_MAX_MISSING_STEPS)
    parser.add_argument("--frames-per-step", type=int, default=DEFAULT_FRAMES_PER_STEP)
    parser.add_argument("--post-stop-settle", type=float, default=DEFAULT_POST_STOP_SETTLE)
    parser.add_argument("--pre-capture-settle", type=float, default=DEFAULT_PRE_CAPTURE_SETTLE)
    parser.add_argument("--capture-sample-interval", type=float, default=DEFAULT_CAPTURE_SAMPLE_INTERVAL)
    parser.add_argument("--capture-warmup-frames", type=int, default=DEFAULT_CAPTURE_WARMUP_FRAMES)
    parser.add_argument("--no-save-frames", action="store_true")
    args = parser.parse_args(argv)

    if not args.no_motion:
        print("WARNING: motion is enabled. Clear the path and keep one hand near the power switch.")
        time.sleep(2)

    report = run_demo(
        output_dir=args.output_dir,
        prepare=(not args.skip_prepare),
        init_gimbal=(not args.skip_gimbal_init),
        require_gimbal=(not args.allow_gimbal_failure),
        home_pan=args.home_pan,
        home_tilt=args.home_tilt,
        gimbal_hold_seconds=args.gimbal_hold_seconds,
        enable_motion=(not args.no_motion),
        camera_width=args.camera_width,
        camera_height=args.camera_height,
        target_role=args.target_role,
        target_station=args.target_station,
        stop_width_px=args.stop_width_px,
        stop_width_ratio=args.stop_width_ratio,
        qr_real_width_mm=args.qr_real_width_mm,
        focal_px=args.focal_px,
        step_speed=args.step_speed,
        step_duration=args.step_duration,
        fine_step_speed=args.fine_step_speed,
        fine_step_duration=args.fine_step_duration,
        fine_width_ratio=args.fine_width_ratio,
        late_step_duration=args.late_step_duration,
        slow_after_steps=args.slow_after_steps,
        micro_step_speed=args.micro_step_speed,
        micro_step_duration=args.micro_step_duration,
        micro_width_ratio=args.micro_width_ratio,
        motor_kick_speed=args.motor_kick_speed,
        motor_kick_duration=args.motor_kick_duration,
        enable_backoff=args.enable_backoff,
        backoff_width_ratio=args.backoff_width_ratio,
        backoff_speed=args.backoff_speed,
        backoff_duration=args.backoff_duration,
        max_steps=args.max_steps,
        max_missing_steps=args.max_missing_steps,
        frames_per_step=args.frames_per_step,
        post_stop_settle=args.post_stop_settle,
        pre_capture_settle=args.pre_capture_settle,
        capture_sample_interval=args.capture_sample_interval,
        capture_warmup_frames=args.capture_warmup_frames,
        save_frames=(not args.no_save_frames),
    )
    print(summarize_report(report))
    return 0 if report.get("stop_reason") != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
