#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jetbot initialization + system self-check.

Run on Jetbot:
    python3 jetbot_init_and_selfcheck.py

What it does:
1. Use the default public Yahboom sudo password.
2. Stop the official Yahboom app service: jetbot_start.
3. Restart the camera service: nvargus-daemon.
4. Run system checks for Python, services, /dev/video*, internet, key files,
   Robot API and Camera API.

The default password is stored in this script as requested. It is not written
to generated reports.
Stopping jetbot_start here is temporary. It does not disable the service
permanently.
"""

from __future__ import print_function

import argparse
import getpass
import glob
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request


DEFAULT_SUDO_PASSWORD = "yahboom"


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def run_cmd(cmd, timeout=10, stdin_text=None):
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
    except subprocess.TimeoutExpired:
        try:
            p.kill()
        except Exception:
            pass
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": "Timeout after {} seconds".format(timeout),
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


def sudo_cmd(args, password, timeout=15):
    stdin_text = None
    if password is not None:
        stdin_text = password + "\n"
    return run_cmd(
        ["sudo", "-S", "-p", ""] + list(args),
        timeout=timeout,
        stdin_text=stdin_text,
    )


def get_sudo_password(non_interactive=False, prompt_password=False):
    env_password = os.environ.get("JETBOT_SUDO_PASSWORD")
    if env_password:
        return env_password
    if prompt_password and not non_interactive:
        return getpass.getpass("请输入 Jetbot sudo 密码：")
    return DEFAULT_SUDO_PASSWORD


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
        found[pattern] = sorted(set(matches))[:30]
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
            result.update({
                "motion_test": True,
                "motion_speed": speed,
                "motion_duration": duration,
            })

        return result
    except Exception as exc:
        return {
            "ok": False,
            "error": repr(exc),
            "hint": "If Robot fails, stop other control notebooks and confirm the official basic motion notebook still works.",
        }


def _check_camera_once(width=224, height=224, image_path="init_selfcheck_frame.jpg"):
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
            }

        saved = False
        try:
            import cv2

            saved = bool(cv2.imwrite(image_path, frame))
        except Exception as exc:
            return {
                "ok": False,
                "error": "cv2.imwrite failed: " + repr(exc),
            }

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
        }
    finally:
        if camera is not None:
            try:
                camera.stop()
            except Exception:
                pass


def check_camera(width=224, height=224, image_path="init_selfcheck_frame.jpg"):
    first = _check_camera_once(width=width, height=height, image_path=image_path)
    if first.get("ok"):
        first["attempts"] = 1
        return first

    time.sleep(2)
    second = _check_camera_once(width=width, height=height, image_path=image_path)
    second["attempts"] = 2
    second["first_error"] = first.get("error")
    if not second.get("ok"):
        second["hint"] = (
            "Camera failed after initialization. Close other camera notebooks/kernels, "
            "rerun this script, or reboot Jetbot if nvargus-daemon is still unstable."
        )
    return second


def initialize_system(password, wait_seconds=5, skip_init=False):
    steps = []

    if skip_init:
        return {
            "ok": True,
            "skipped": True,
            "steps": steps,
        }

    sudo_check = sudo_cmd(["-v"], password, timeout=10)
    steps.append({
        "name": "sudo_validate",
        "result": sudo_check,
    })

    if not sudo_check.get("ok"):
        return {
            "ok": False,
            "skipped": False,
            "steps": steps,
            "hint": "Sudo validation failed. Check the password and rerun.",
        }

    before_jetbot_start = check_service("jetbot_start")
    stop_service = sudo_cmd(["systemctl", "stop", "jetbot_start"], password, timeout=15)
    after_jetbot_start = check_service("jetbot_start")
    steps.append({
        "name": "stop_jetbot_start",
        "before": before_jetbot_start,
        "command": stop_service,
        "after": after_jetbot_start,
        "note": "inactive is expected during custom development.",
    })

    restart_camera = sudo_cmd(["systemctl", "restart", "nvargus-daemon"], password, timeout=20)
    time.sleep(wait_seconds)
    after_nvargus = check_service("nvargus-daemon")
    steps.append({
        "name": "restart_nvargus_daemon",
        "command": restart_camera,
        "after": after_nvargus,
        "note": "active is expected after restart.",
    })

    ok = sudo_check.get("ok") and stop_service.get("ok") and restart_camera.get("ok")
    return {
        "ok": ok,
        "skipped": False,
        "steps": steps,
    }


def summarize(report):
    failed = []
    checks = report.get("checks", {})
    required = ["python", "robot", "camera", "internet"]
    for name in required:
        if not checks.get(name, {}).get("ok"):
            failed.append(name)

    init_ok = report.get("initialization", {}).get("ok")
    if not init_ok:
        failed.insert(0, "initialization")

    if failed:
        return {
            "ok": False,
            "message": "Checks failed: " + ", ".join(failed),
        }
    return {
        "ok": True,
        "message": "Initialization and core checks passed.",
    }


def write_text_report(report, path):
    lines = []
    lines.append("Jetbot Initialization + System Self-check")
    lines.append("Time: {}".format(report["time"]))
    lines.append("")
    lines.append("Summary: {}".format(report["summary"]["message"]))
    lines.append("")

    lines.append("== initialization ==")
    lines.append(json.dumps(report.get("initialization", {}), ensure_ascii=False, indent=2))
    lines.append("")

    for name, value in report.get("checks", {}).items():
        lines.append("== {} ==".format(name))
        lines.append(json.dumps(value, ensure_ascii=False, indent=2))
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def build_report(args, password):
    report = {
        "time": now(),
        "initialization": {},
        "checks": {},
        "notes": [
            "The default public sudo password is stored in the script as requested, but is not saved in this report.",
            "Stopping jetbot_start is temporary and does not permanently disable the official app service.",
        ],
    }

    report["initialization"] = initialize_system(
        password=password,
        wait_seconds=args.wait_seconds,
        skip_init=args.skip_init,
    )

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
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-init", action="store_true", help="Run checks without sudo initialization.")
    parser.add_argument("--non-interactive", action="store_true", help="Do not prompt for password; use default password or JETBOT_SUDO_PASSWORD.")
    parser.add_argument("--prompt-password", action="store_true", help="Prompt for sudo password instead of using the default public password.")
    parser.add_argument("--wait-seconds", type=int, default=5)
    parser.add_argument("--camera-width", type=int, default=224)
    parser.add_argument("--camera-height", type=int, default=224)
    parser.add_argument("--image-path", default="init_selfcheck_frame.jpg")
    parser.add_argument("--internet-url", default="https://www.baidu.com")
    parser.add_argument("--internet-timeout", type=int, default=8)
    parser.add_argument("--json-report", default="jetbot_init_selfcheck_report.json")
    parser.add_argument("--text-report", default="jetbot_init_selfcheck_report.txt")
    parser.add_argument("--motion-test", action="store_true", help="Run a short forward motion test.")
    parser.add_argument("--motion-speed", type=float, default=0.35)
    parser.add_argument("--motion-duration", type=float, default=0.35)
    args = parser.parse_args(argv)

    if args.motion_test:
        print("WARNING: motion test enabled. Lift the tracks or clear the area.")
        time.sleep(2)

    password = None
    if not args.skip_init:
        password = get_sudo_password(
            non_interactive=args.non_interactive,
            prompt_password=args.prompt_password,
        )

    report = build_report(args, password)

    with open(args.json_report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    write_text_report(report, args.text_report)

    print(report["summary"]["message"])
    print("JSON report:", args.json_report)
    print("Text report:", args.text_report)
    if report["checks"].get("camera", {}).get("image_saved"):
        print("Camera frame:", report["checks"]["camera"].get("image_path"))

    return 0 if report["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
