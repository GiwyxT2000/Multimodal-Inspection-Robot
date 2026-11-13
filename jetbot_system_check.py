#!/usr/bin/env python3
"""
Jetbot system self-check script.

Run on Jetbot:
    python3 jetbot_system_check.py

Optional motion test, use only when the tracks are lifted or the area is clear:
    python3 jetbot_system_check.py --motion-test
"""

import argparse
import glob
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def run_cmd(cmd, timeout=8):
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            universal_newlines=True,
        )
        return {
            "ok": p.returncode == 0,
            "returncode": p.returncode,
            "stdout": p.stdout.strip(),
            "stderr": p.stderr.strip(),
        }
    except Exception as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": repr(exc),
        }


def check_python():
    return {
        "ok": True,
        "version": sys.version.replace("\n", " "),
        "executable": sys.executable,
        "platform": platform.platform(),
    }


def check_service(name):
    result = run_cmd(["systemctl", "is-active", name], timeout=5)
    state = result["stdout"] or result["stderr"]
    return {
        "ok": result["ok"],
        "service": name,
        "state": state,
        "expected_note": "inactive is OK for jetbot_start during development; active is OK for nvargus-daemon and jetbot_jupyter.",
    }


def check_dev_video():
    devices = sorted(glob.glob("/dev/video*"))
    return {
        "ok": len(devices) > 0,
        "devices": devices,
    }


def check_internet(url, timeout):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return {
                "ok": True,
                "url": url,
                "status": resp.status,
            }
    except Exception as exc:
        return {
            "ok": False,
            "url": url,
            "error": repr(exc),
        }


def find_paths(patterns, roots):
    found = {}
    for pattern in patterns:
        matches = []
        for root in roots:
            for path in glob.glob(os.path.join(root, "**", pattern), recursive=True):
                matches.append(path)
        found[pattern] = sorted(set(matches))[:20]
    return {
        "ok": any(found[p] for p in found),
        "found": found,
    }


def check_robot(motion_test=False, speed=0.35, duration=0.35):
    try:
        from jetbot import Robot

        robot = Robot()
        robot.stop()
        result = {
            "ok": True,
            "import_ok": True,
            "instantiated": True,
            "stop_ok": True,
            "motion_test": False,
        }

        if motion_test:
            robot.forward(speed)
            time.sleep(duration)
            robot.stop()
            result.update(
                {
                    "motion_test": True,
                    "motion_speed": speed,
                    "motion_duration": duration,
                }
            )

        return result
    except Exception as exc:
        return {
            "ok": False,
            "error": repr(exc),
            "hint": "If Robot import fails, open the official basic motion notebook and confirm the jetbot package path.",
        }


def restart_nvargus(wait_seconds=4):
    result = run_cmd(["sudo", "systemctl", "restart", "nvargus-daemon"], timeout=12)
    time.sleep(wait_seconds)
    return result


def _check_camera_once(width=224, height=224, image_path="selfcheck_frame.jpg"):
    camera = None
    try:
        from jetbot import Camera

        camera = Camera.instance(width=width, height=height)
        time.sleep(2)
        frame = camera.value
        shape = getattr(frame, "shape", None)

        if frame is None:
            return {
                "ok": False,
                "error": "camera.value is None",
                "hint": "Try: sudo systemctl restart nvargus-daemon, then restart the Jupyter kernel.",
            }

        saved = False
        try:
            import cv2

            saved = bool(cv2.imwrite(image_path, frame))
        except Exception:
            saved = False

        return {
            "ok": True,
            "width": width,
            "height": height,
            "frame_shape": list(shape) if shape is not None else None,
            "image_saved": saved,
            "image_path": image_path if saved else None,
            "camera_released": True,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": repr(exc),
            "hint": "Common fix: sudo systemctl stop jetbot_start; sudo systemctl restart nvargus-daemon; restart Jupyter kernel.",
        }
    finally:
        if camera is not None:
            try:
                camera.stop()
            except Exception:
                pass


def check_camera(width=224, height=224, image_path="selfcheck_frame.jpg"):
    first = _check_camera_once(width=width, height=height, image_path=image_path)
    if first.get("ok"):
        first["attempts"] = 1
        return first

    restart = restart_nvargus(wait_seconds=5)
    second = _check_camera_once(width=width, height=height, image_path=image_path)
    second["attempts"] = 2
    second["first_error"] = first.get("error")
    second["nvargus_restart"] = restart
    if not second.get("ok"):
        second["hint"] = (
            "Camera still failed after retry. Shutdown other camera notebooks/kernels, "
            "run sudo systemctl restart nvargus-daemon in terminal, then restart this kernel."
        )
    return second


def summarize(report):
    required = [
        ("python", report["checks"].get("python", {}).get("ok")),
        ("robot", report["checks"].get("robot", {}).get("ok")),
        ("camera", report["checks"].get("camera", {}).get("ok")),
        ("internet", report["checks"].get("internet", {}).get("ok")),
    ]
    failed = [name for name, ok in required if not ok]
    if failed:
        return {
            "ok": False,
            "message": "Core checks failed: " + ", ".join(failed),
        }
    return {
        "ok": True,
        "message": "Core checks passed: Python, Robot, Camera, Internet.",
    }


def write_text_report(report, path):
    lines = []
    lines.append("Jetbot System Self-check")
    lines.append("Time: {}".format(report["time"]))
    lines.append("")
    lines.append("Summary: {}".format(report["summary"]["message"]))
    lines.append("")
    for name, value in report["checks"].items():
        lines.append("== {} ==".format(name))
        lines.append(json.dumps(value, ensure_ascii=False, indent=2))
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--motion-test", action="store_true", help="Run a short forward movement test.")
    parser.add_argument("--motion-speed", type=float, default=0.35)
    parser.add_argument("--motion-duration", type=float, default=0.35)
    parser.add_argument("--camera-width", type=int, default=224)
    parser.add_argument("--camera-height", type=int, default=224)
    parser.add_argument("--image-path", default="selfcheck_frame.jpg")
    parser.add_argument("--internet-url", default="https://www.baidu.com")
    parser.add_argument("--internet-timeout", type=int, default=8)
    parser.add_argument("--json-report", default="jetbot_selfcheck_report.json")
    parser.add_argument("--text-report", default="jetbot_selfcheck_report.txt")
    args = parser.parse_args()

    if args.motion_test:
        print("WARNING: motion test enabled. Lift the tracks or clear the area.")
        time.sleep(2)

    report = {
        "time": now(),
        "checks": {},
    }

    checks = report["checks"]
    checks["python"] = check_python()
    checks["jetbot_start"] = check_service("jetbot_start")
    checks["nvargus_daemon"] = check_service("nvargus-daemon")
    checks["jetbot_jupyter"] = check_service("jetbot_jupyter")
    checks["dev_video"] = check_dev_video()
    checks["internet"] = check_internet(args.internet_url, args.internet_timeout)
    checks["files"] = find_paths(
        ["robot.py", "RGB_Lib.py", "servoserial.py", "*.ipynb"],
        ["/home/jetbot"],
    )
    checks["robot"] = check_robot(
        motion_test=args.motion_test,
        speed=args.motion_speed,
        duration=args.motion_duration,
    )
    checks["camera"] = check_camera(
        width=args.camera_width,
        height=args.camera_height,
        image_path=args.image_path,
    )

    report["summary"] = summarize(report)

    with open(args.json_report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    write_text_report(report, args.text_report)

    print(report["summary"]["message"])
    print("JSON report:", args.json_report)
    print("Text report:", args.text_report)
    if checks["camera"].get("image_saved"):
        print("Camera frame:", checks["camera"].get("image_path"))

    return 0 if report["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
