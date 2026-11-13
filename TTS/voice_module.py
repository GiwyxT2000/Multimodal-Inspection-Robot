#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UART wrapper for the Yahboom AI voice module.

Protocol:
  Passive broadcast: AA 55 FF <broadcast_id> FB
  Recognition frame: AA 55 <function_id> <command_id> FB
"""

from __future__ import print_function

import glob
import time


BROADCAST_COMMANDS = {
    # Aliases from the vendor Jetson UART sample. Keep them because firmware
    # revisions may differ from the spreadsheet protocol list.
    "this_red": 0x60,
    "this_green": 0x61,
    "this_yellow": 0x62,
    "recognize_yellow": 0x63,
    "recognize_green": 0x64,
    "recognize_blue": 0x65,
    "recognize_red": 0x66,
    "init": 0x67,
    # Passive broadcast phrases from 命令词播报词协议列表V3_中文.xlsx.
    "xlsx_this_red": 0x3D,
    "xlsx_this_blue": 0x3E,
    "xlsx_this_green": 0x3F,
    "xlsx_this_yellow": 0x40,
    "place_done": 0x41,
    "xlsx_recognize_yellow": 0x42,
    "xlsx_recognize_green": 0x43,
    "xlsx_recognize_blue": 0x44,
    "xlsx_recognize_red": 0x49,
    "init_xlsx": 0x58,
    "can_start_action_input": 0x1D,
    "just_grabbed": 0x22,
    "recyclable_can": 0x5E,
    "recyclable_old_bag": 0x5F,
    "recyclable_newspaper": 0x60,
    "recyclable_book": 0x61,
    "hazardous_syringe": 0x62,
    "hazardous_battery": 0x63,
    "hazardous_cosmetics": 0x64,
    "hazardous_medicine": 0x65,
    "wet_fishbone": 0x66,
    "wet_watermelon_peel": 0x67,
    "wet_apple_core": 0x68,
    "wet_eggshell": 0x69,
    "dry_chopsticks": 0x6A,
    "dry_cigarette": 0x6B,
    "dry_peach_pit": 0x6C,
    "dry_tissue": 0x5D,
}


FUNCTION_IDS = {
    0x01: "welcome",
    0x02: "sleep",
    0x03: "wake",
    0x04: "volume_up",
    0x05: "volume_down",
    0x06: "volume_max",
    0x07: "volume_medium",
    0x08: "volume_min",
    0x09: "broadcast_on",
    0x0A: "broadcast_off",
}


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
    0x2B: "夹紧",
    0x2C: "松开",
    0x2D: "鼓掌",
    0x2E: "点头",
    0x2F: "祈祷",
    0x30: "跪下",
    0x31: "初始位置",
    0x32: "惊吓",
    0x33: "叠罗汉",
    0x34: "跳舞",
    0x35: "夹方块",
    0x36: "搬运",
    0x37: "输入完成",
    0x38: "输入结束",
    0x39: "运动动作",
    0x3A: "清除动作",
    0x3C: "这是什么颜色",
    0x3D: "开始颜色分拣",
    0x46: "开始颜色抓取",
    0x47: "开始追踪人脸",
    0x48: "开始追踪黄色",
    0x49: "开始追踪红色",
    0x4A: "开始追踪绿色",
    0x4B: "开始追踪蓝色",
    0x4C: "取消追踪",
    0x4D: "夹取黄色",
    0x4E: "夹取红色",
    0x4F: "夹取绿色",
    0x50: "夹取蓝色",
    0x52: "推倒",
    0x57: "红色",
    0x58: "绿色",
    0x59: "蓝色",
    0x5A: "黄色",
    0x5B: "不要",
    0x5C: "开始分拣",
    0x5E: "这是什么垃圾",
}


BROADCAST_PHRASES = {
    0x1D: "我可以开始动作输入",
    0x22: "我刚夹取了",
    0x3D: "这是红色",
    0x3E: "这是蓝色",
    0x3F: "这是绿色",
    0x40: "这是黄色",
    0x41: "放置完成",
    0x42: "识别到黄色",
    0x43: "识别到绿色",
    0x44: "识别到蓝色",
    0x49: "识别到红色",
    0x58: "初始化完成",
    0x5D: "这是卫生纸,属于干垃圾",
    0x5E: "这是易拉罐,属于可回收垃圾",
    0x5F: "这是旧书包,属于可回收垃圾",
    0x60: "这是报纸,属于可回收垃圾",
    0x61: "这是书本,属于可回收垃圾",
    0x62: "这是注射器,属于有毒垃圾",
    0x63: "这是废旧电池,属于有毒垃圾",
    0x64: "这是过期化妆品,属于有毒垃圾",
    0x65: "这是过期药品,属于有毒垃圾",
    0x66: "这是鱼骨,属于湿垃圾",
    0x67: "这是西瓜皮,属于湿垃圾",
    0x68: "这是苹果核,属于湿垃圾",
    0x69: "这是鸡蛋壳,属于湿垃圾",
    0x6A: "这是一次性筷子,属于干垃圾",
    0x6B: "这是烟蒂,属于干垃圾",
    0x6C: "这是桃核,属于干垃圾",
}


RECOGNITION_IDS = {
    0x01: "car_stop",
    0x02: "stop",
    0x03: "car_sleep",
    0x04: "car_forward",
    0x05: "car_backward",
    0x06: "car_turn_left",
    0x07: "car_turn_right",
    0x08: "car_spin_left",
    0x09: "car_spin_right",
    0x0A: "light_off",
    0x0B: "red_light",
    0x0C: "green_light",
    0x0D: "blue_light",
    0x0E: "yellow_light",
    0x0F: "waterfall_light_on",
    0x10: "gradient_light_on",
    0x11: "breathing_light_on",
    0x12: "show_battery",
    0x13: "track_to_position_1",
    0x14: "track_to_position_2",
    0x15: "track_to_position_3",
    0x16: "line_tracking_off",
    0x17: "track_red_line",
    0x18: "track_green_line",
    0x19: "track_blue_line",
    0x1A: "track_yellow_line",
    0x1B: "following_on",
    0x1C: "following_off",
    0x20: "track_to_position_4",
    0x21: "return_to_origin",
    0x26: "alarm",
    0x27: "look_up",
    0x28: "look_down",
    0x29: "look_left",
    0x2A: "look_right",
    0x2B: "grip",
    0x2C: "release",
    0x31: "home_pose",
    0x3C: "ask_color",
    0x5E: "ask_garbage_type",
}


PROJECT_ACTIONS = {
    0x01: "stop",
    0x02: "stop",
    0x03: "sleep",
    0x04: "start_patrol",
    0x13: "go_station_1",
    0x14: "go_station_2",
    0x15: "go_station_3",
    0x20: "go_station_4",
    0x21: "return_home",
}


def find_uart_ports():
    ports = []
    for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*"]:
        ports.extend(glob.glob(pattern))
    return sorted(set(ports))


def normalize_command_id(command):
    if isinstance(command, str):
        stripped = command.strip()
        key = stripped.lower().replace("-", "_")
        if key in BROADCAST_COMMANDS:
            return BROADCAST_COMMANDS[key]
        for command_id, phrase in BROADCAST_PHRASES.items():
            if stripped == phrase:
                return int(command_id)
        raise ValueError("Unknown broadcast command name: {0}".format(command))
    value = int(command)
    if value < 0 or value > 255:
        raise ValueError("Command id must be one byte: {0}".format(command))
    return value


def build_broadcast_frame(command):
    command_id = normalize_command_id(command)
    return bytes([0xAA, 0x55, 0xFF, command_id, 0xFB])


def parse_frame(frame):
    if len(frame) != 5:
        return None
    if frame[0] != 0xAA or frame[1] != 0x55 or frame[4] != 0xFB:
        return None
    function_id = int(frame[2])
    command_id = int(frame[3])
    return {
        "function_id": function_id,
        "function_name": FUNCTION_IDS.get(function_id),
        "function_word": FUNCTION_WORDS.get(function_id),
        "command_id": command_id,
        "command_name": RECOGNITION_IDS.get(command_id),
        "command_word": COMMAND_WORDS.get(command_id),
        "project_action": PROJECT_ACTIONS.get(command_id),
        "raw_hex": frame.hex(),
    }


class VoiceModule(object):
    def __init__(self, port=None, baudrate=115200, timeout=0.05):
        self.port = port
        self.baudrate = int(baudrate)
        self.timeout = float(timeout)
        self.serial = None
        self._buffer = bytearray()

    def open(self):
        if self.port is None:
            ports = find_uart_ports()
            if not ports:
                raise RuntimeError("No voice-module UART port found under /dev/ttyUSB* or /dev/ttyACM*.")
            self.port = ports[0]

        import serial

        self.serial = serial.Serial(
            self.port,
            self.baudrate,
            timeout=self.timeout,
            write_timeout=1,
        )
        return {
            "ok": bool(self.serial.isOpen() if hasattr(self.serial, "isOpen") else self.serial.is_open),
            "port": self.port,
            "baudrate": self.baudrate,
        }

    def close(self):
        if self.serial is not None:
            try:
                self.serial.close()
            except Exception:
                pass
        self.serial = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

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
        frame = build_broadcast_frame(command)
        self.serial.write(frame)
        time.sleep(0.005)
        command_id = normalize_command_id(command)
        return {
            "ok": True,
            "command": command,
            "command_id": command_id,
            "phrase": BROADCAST_PHRASES.get(command_id),
            "frame_hex": frame.hex(),
        }

    def _read_available(self):
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
        data = self._read_available()
        if data:
            self._buffer.extend(data)

        frames = []
        while len(self._buffer) >= 5:
            if self._buffer[0] != 0xAA or self._buffer[1] != 0x55:
                del self._buffer[0]
                continue

            frame = bytes(self._buffer[:5])
            if frame[4] != 0xFB:
                del self._buffer[0]
                continue

            del self._buffer[:5]
            parsed = parse_frame(frame)
            if parsed is not None:
                frames.append(parsed)

        return frames

    def read_command(self, timeout_seconds=0.0, ignore_ids=None):
        if ignore_ids is None:
            ignore_ids = []
        ignore_ids = set(int(item) for item in ignore_ids)

        deadline = time.time() + float(timeout_seconds)
        while True:
            frames = self.poll_frames()
            for frame in frames:
                if int(frame["command_id"]) not in ignore_ids:
                    return frame

            if timeout_seconds is None:
                time.sleep(0.02)
                continue
            if float(timeout_seconds) <= 0:
                return None
            if time.time() >= deadline:
                return None
            time.sleep(0.02)

    def wait_command(self, timeout_seconds=None, ignore_ids=None):
        return self.read_command(timeout_seconds=timeout_seconds, ignore_ids=ignore_ids)
