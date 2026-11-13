#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Voice command and fixed broadcast tool for the Yahboom AI voice module.

The module firmware only supports fixed recognition words and fixed passive
broadcast phrases.  This tool wraps the stock UART protocol for our inspection
demo:

Recognition: AA 55 <function_id> <command_id> FB
Broadcast:   AA 55 FF <broadcast_id> FB
"""

from __future__ import print_function

import argparse
import glob
import json
import os
import time


DEFAULT_OUTPUT_DIR = "voice_control_output"
DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT = 0.05
DEFAULT_LISTEN_SECONDS = 30.0
DEFAULT_OPEN_SETTLE = 0.30


FUNCTION_WORDS = {
    0x01: "欢迎语",
    0x02: "休息语",
    0x03: "你好小亚",
    0x04: "增大音量",
    0x05: "减小音量",
    0x06: "最大音量",
    0x07: "中等音量",
    0x08: "最小音量",
    0x09: "开启播报",
    0x0A: "关闭播报",
}


COMMAND_WORDS = {
    0x01: "小车停车",
    0x02: "停车",
    0x03: "小车休眠",
    0x04: "小车前进",
    0x05: "小车后退",
    0x06: "小车左转",
    0x07: "小车右转",
    0x08: "小车左旋",
    0x09: "小车右旋",
    0x0A: "关灯",
    0x0B: "亮红灯",
    0x0C: "亮绿灯",
    0x0D: "亮蓝灯",
    0x0E: "亮黄灯",
    0x0F: "打开流水灯",
    0x10: "打开渐变灯",
    0x11: "打开呼吸灯",
    0x12: "显示电量",
    0x13: "导航去一号位",
    0x14: "导航去二号位",
    0x15: "导航去三号位",
    0x16: "关闭巡线",
    0x17: "巡红线",
    0x18: "巡绿线",
    0x19: "巡蓝线",
    0x1A: "巡黄线",
    0x1B: "开启跟随",
    0x1C: "关闭跟随",
    0x20: "导航去四号位",
    0x21: "回到原点",
    0x26: "报警",
    0x27: "向上",
    0x28: "向下",
    0x29: "向左",
    0x2A: "向右",
    0x31: "初始位置",
}


PROJECT_ACTIONS = {
    0x01: "stop",
    0x02: "stop",
    0x03: "sleep",
    0x04: "start_inspection",
    0x13: "start_inspection",
    0x14: "start_inspection",
    0x15: "start_inspection",
    0x20: "start_inspection",
    0x21: "return_home",
    0x26: "manual_alarm",
}


BROADCAST_PHRASES = {
    # IDs from the vendor Jetson UART tutorial. Some shipped firmware uses
    # this older table even when the V3 spreadsheet is included in the package.
    "legacy_this_red": (0x60, "这是红色"),
    "legacy_this_green": (0x61, "这是绿色"),
    "legacy_this_yellow": (0x62, "这是黄色"),
    "legacy_recognized_yellow": (0x63, "识别到黄色"),
    "legacy_recognized_green": (0x64, "识别到绿色"),
    "legacy_recognized_blue": (0x65, "识别到蓝色"),
    "legacy_recognized_red": (0x66, "识别到红色"),
    "legacy_init": (0x67, "初始化完成"),
    # IDs from 命令词播报词协议列表V3_中文.xlsx.
    "this_red": (0x3D, "这是红色"),
    "this_blue": (0x3E, "这是蓝色"),
    "this_green": (0x3F, "这是绿色"),
    "this_yellow": (0x40, "这是黄色"),
    "place_done": (0x41, "放置完成"),
    "recognized_yellow": (0x42, "识别到黄色"),
    "recognized_green": (0x43, "识别到绿色"),
    "recognized_blue": (0x44, "识别到蓝色"),
    "recognized_red": (0x49, "识别到红色"),
    "init_done": (0x58, "初始化完成"),
    "can_start_action": (0x1D, "我可以开始动作输入"),
}


RISK_BROADCAST = {
    # Verified on the actual module firmware by direct serial writes.
    # The "this color" IDs are inconsistent on this module: 0x60 speaks
    # "这是蓝色".  The "recognized color" IDs are stable enough for risk
    # feedback: 0x64 green, 0x63 yellow, 0x66 red.
    "normal": 0x64,
    "warning": 0x63,
    "abnormal": 0x66,
}


START_ACTIONS = set(["start_inspection"])


def now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def ensure_dir(path):
    if path and not os.path.isdir(path):
        os.makedirs(path)


def find_uart_ports():
    ports = []
    for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*"]:
        ports.extend(glob.glob(pattern))
    return sorted(set(ports))


def frame_hex(frame):
    return " ".join("{:02X}".format(item) for item in bytearray(frame))


def normalize_broadcast(command):
    if isinstance(command, str):
        key = command.strip().lower().replace("-", "_")
        if key in BROADCAST_PHRASES:
            command_id, phrase = BROADCAST_PHRASES[key]
            return command_id, key, phrase
        for name, item in BROADCAST_PHRASES.items():
            if command.strip() == item[1]:
                return item[0], name, item[1]
        raise ValueError("Unknown broadcast phrase: {0}".format(command))

    command_id = int(command)
    if command_id < 0 or command_id > 255:
        raise ValueError("Broadcast id must be one byte.")
    for name, item in BROADCAST_PHRASES.items():
        if item[0] == command_id:
            return command_id, name, item[1]
    return command_id, "custom_{:02x}".format(command_id), None


def build_broadcast_frame(command):
    command_id, name, phrase = normalize_broadcast(command)
    return bytes([0xAA, 0x55, 0xFF, command_id, 0xFB]), name, phrase


def parse_frame(frame):
    data = bytearray(frame)
    if len(data) != 5:
        return None
    if data[0] != 0xAA or data[1] != 0x55 or data[4] != 0xFB:
        return None

    function_id = int(data[2])
    command_id = int(data[3])
    return {
        "function_id": function_id,
        "function_word": FUNCTION_WORDS.get(function_id),
        "command_id": command_id,
        "command_word": COMMAND_WORDS.get(command_id),
        "project_action": PROJECT_ACTIONS.get(command_id),
        "raw_hex": frame_hex(data),
    }


class VoiceControl(object):
    def __init__(self, port=None, baudrate=DEFAULT_BAUDRATE, timeout=DEFAULT_TIMEOUT):
        self.port = port
        self.baudrate = int(baudrate)
        self.timeout = float(timeout)
        self.serial = None
        self.buffer = bytearray()

    def open(self):
        if self.port is None:
            ports = find_uart_ports()
            if not ports:
                raise RuntimeError("No UART port found under /dev/ttyUSB* or /dev/ttyACM*.")
            self.port = ports[0]

        import serial

        self.serial = serial.Serial(
            self.port,
            self.baudrate,
            timeout=self.timeout,
            write_timeout=1,
        )
        time.sleep(DEFAULT_OPEN_SETTLE)
        ok = bool(self.serial.isOpen() if hasattr(self.serial, "isOpen") else self.serial.is_open)
        return {"ok": ok, "port": self.port, "baudrate": self.baudrate}

    def close(self):
        if self.serial is not None:
            try:
                self.serial.close()
            except Exception:
                pass
        self.serial = None

    def reset_input(self):
        if self.serial is None:
            return
        if hasattr(self.serial, "reset_input_buffer"):
            self.serial.reset_input_buffer()
        else:
            self.serial.flushInput()

    def speak(self, command):
        if self.serial is None:
            self.open()
        frame, name, phrase = build_broadcast_frame(command)
        self.serial.write(frame)
        time.sleep(0.005)
        return {
            "ok": True,
            "time": now_text(),
            "type": "broadcast",
            "name": name,
            "phrase": phrase,
            "frame_hex": frame_hex(frame),
        }

    def speak_risk(self, risk_level):
        level = (risk_level or "warning").strip().lower()
        command = RISK_BROADCAST.get(level, RISK_BROADCAST["warning"])
        event = self.speak(command)
        event["risk_level"] = level
        return event

    def read_available(self):
        if self.serial is None:
            self.open()
        try:
            count = int(self.serial.in_waiting)
        except Exception:
            count = int(self.serial.inWaiting())
        if count <= 0:
            return b""
        return self.serial.read(count)

    def poll_frames(self):
        data = self.read_available()
        if data:
            self.buffer.extend(data)

        frames = []
        while len(self.buffer) >= 5:
            if self.buffer[0] != 0xAA or self.buffer[1] != 0x55:
                del self.buffer[0]
                continue
            raw = bytes(self.buffer[:5])
            if raw[4] != 0xFB:
                del self.buffer[0]
                continue
            del self.buffer[:5]
            parsed = parse_frame(raw)
            if parsed:
                parsed["time"] = now_text()
                frames.append(parsed)
        return frames

    def wait_command(self, timeout_seconds=DEFAULT_LISTEN_SECONDS, ignore_command_ids=None):
        if ignore_command_ids is None:
            ignore_command_ids = []
        ignored = set(int(item) for item in ignore_command_ids)
        deadline = time.time() + float(timeout_seconds)
        while time.time() < deadline:
            for frame in self.poll_frames():
                if int(frame["command_id"]) not in ignored:
                    return frame
            time.sleep(0.02)
        return None


def write_report(report, output_dir):
    ensure_dir(output_dir)
    report["finished_at"] = now_text()
    json_path = os.path.join(output_dir, "voice_control_report.json")
    txt_path = os.path.join(output_dir, "voice_control_report.txt")
    report["report_json"] = json_path
    report["report_txt"] = txt_path
    with open(json_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(txt_path, "w") as f:
        f.write("Voice Control Tool\n")
        f.write("Summary: {0}\n".format(report.get("summary")))
        f.write("Triggered: {0}\n".format(report.get("triggered")))
        f.write("Action: {0}\n".format(report.get("action")))
        f.write("JSON report: {0}\n".format(json_path))
    return report


def run_demo(output_dir=DEFAULT_OUTPUT_DIR,
             port=None,
             baudrate=DEFAULT_BAUDRATE,
             listen_seconds=DEFAULT_LISTEN_SECONDS,
             init_broadcast=True,
             ready_broadcast=False,
             risk_level=None,
             broadcast_only=False,
             probe_broadcast=False,
             probe_colors=False,
             raw_monitor=False,
             dry_run=False):
    report = {
        "demo": "voice_control_tool",
        "started_at": now_text(),
        "summary": None,
        "triggered": False,
        "action": None,
        "config": {
            "output_dir": output_dir,
            "port": port,
            "baudrate": baudrate,
            "listen_seconds": listen_seconds,
            "init_broadcast": bool(init_broadcast),
            "ready_broadcast": bool(ready_broadcast),
            "risk_level": risk_level,
            "broadcast_only": bool(broadcast_only),
            "probe_broadcast": bool(probe_broadcast),
            "probe_colors": bool(probe_colors),
            "raw_monitor": bool(raw_monitor),
            "dry_run": bool(dry_run),
        },
        "ports": find_uart_ports(),
        "events": [],
        "error": None,
    }

    if dry_run:
        init_frame, init_name, init_phrase = build_broadcast_frame("legacy_init")
        risk_command = RISK_BROADCAST.get((risk_level or "warning").lower(), RISK_BROADCAST["warning"])
        risk_frame, risk_name, risk_phrase = build_broadcast_frame(risk_command)
        report["events"].append({
            "type": "dry_run_frame",
            "name": init_name,
            "phrase": init_phrase,
            "frame_hex": frame_hex(init_frame),
        })
        report["events"].append({
            "type": "dry_run_frame",
            "name": risk_name,
            "phrase": risk_phrase,
            "risk_level": risk_level or "warning",
            "frame_hex": frame_hex(risk_frame),
        })
        report["summary"] = "Dry run completed."
        return write_report(report, output_dir)

    module = VoiceControl(port=port, baudrate=baudrate)
    try:
        opened = module.open()
        report["opened"] = opened
        module.reset_input()

        if init_broadcast:
            report["events"].append(module.speak("legacy_init"))
        if ready_broadcast:
            report["events"].append(module.speak("can_start_action"))

        if raw_monitor:
            deadline = time.time() + float(listen_seconds)
            raw_events = []
            while time.time() < deadline:
                data = module.read_available()
                if data:
                    event = {
                        "type": "raw_uart",
                        "time": now_text(),
                        "raw_hex": frame_hex(data),
                        "byte_count": len(data),
                    }
                    raw_events.append(event)
                    report["events"].append(event)
                time.sleep(0.02)
            report["summary"] = "Raw UART monitor completed."
            report["raw_event_count"] = len(raw_events)
            return write_report(report, output_dir)

        if probe_broadcast:
            for command in [
                "legacy_init",
                "legacy_this_red",
                "legacy_this_green",
                "legacy_this_yellow",
                "init_done",
                "this_red",
            ]:
                report["events"].append(module.speak(command))
                time.sleep(0.8)
            report["summary"] = "Broadcast probe completed."
            return write_report(report, output_dir)

        if probe_colors:
            # Probe likely color broadcast IDs on this firmware.  The vendor
            # variable names are not reliable across firmware revisions, so the
            # operator should listen and map the actual spoken color.
            for command_id in [0x3D, 0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43, 0x44, 0x49,
                               0x5F, 0x60, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66, 0x67]:
                event = module.speak(command_id)
                event["probe_id_hex"] = "0x{0:02X}".format(command_id)
                report["events"].append(event)
                print("Probe sent 0x{0:02X}, phrase_hint={1}".format(command_id, event.get("phrase")))
                time.sleep(1.0)
            report["summary"] = "Color broadcast probe completed."
            return write_report(report, output_dir)

        if risk_level or broadcast_only:
            report["events"].append(module.speak_risk(risk_level or "warning"))
            if broadcast_only:
                report["summary"] = "Broadcast test completed."
                return write_report(report, output_dir)

        command = module.wait_command(timeout_seconds=listen_seconds, ignore_command_ids=[0])
        if command is None:
            report["summary"] = "No voice command received before timeout."
            return write_report(report, output_dir)

        report["events"].append({"type": "recognition", "frame": command})
        action = command.get("project_action")
        report["action"] = action
        report["triggered"] = action in START_ACTIONS
        if report["triggered"]:
            report["summary"] = "Start inspection command received."
        else:
            report["summary"] = "Voice command received, but it is not a start command."
        return write_report(report, output_dir)
    except Exception as exc:
        report["error"] = repr(exc)
        report["summary"] = "Error: {0}".format(repr(exc))
        return write_report(report, output_dir)
    finally:
        module.close()


def print_report(report):
    print("Voice Control Tool")
    print("Summary: {0}".format(report.get("summary")))
    print("Triggered: {0}".format(report.get("triggered")))
    print("Action: {0}".format(report.get("action")))
    if report.get("error"):
        print("Error: {0}".format(report.get("error")))
    print("JSON report: {0}".format(report.get("report_json")))
    print("Text report: {0}".format(report.get("report_txt")))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--port", default=None)
    parser.add_argument("--baudrate", type=int, default=DEFAULT_BAUDRATE)
    parser.add_argument("--listen-seconds", type=float, default=DEFAULT_LISTEN_SECONDS)
    parser.add_argument("--no-init-broadcast", action="store_true")
    parser.add_argument("--ready-broadcast", action="store_true")
    parser.add_argument("--risk-level", default=None, choices=["normal", "warning", "abnormal"])
    parser.add_argument("--broadcast-only", action="store_true")
    parser.add_argument("--probe-broadcast", action="store_true")
    parser.add_argument("--probe-colors", action="store_true")
    parser.add_argument("--raw-monitor", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list-phrases", action="store_true")
    args = parser.parse_args(argv)

    if args.list_phrases:
        print(json.dumps(BROADCAST_PHRASES, ensure_ascii=False, indent=2))
        return 0

    report = run_demo(
        output_dir=args.output_dir,
        port=args.port,
        baudrate=args.baudrate,
        listen_seconds=args.listen_seconds,
        init_broadcast=(not args.no_init_broadcast),
        ready_broadcast=args.ready_broadcast,
        risk_level=args.risk_level,
        broadcast_only=args.broadcast_only,
        probe_broadcast=args.probe_broadcast,
        probe_colors=args.probe_colors,
        raw_monitor=args.raw_monitor,
        dry_run=args.dry_run,
    )
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
