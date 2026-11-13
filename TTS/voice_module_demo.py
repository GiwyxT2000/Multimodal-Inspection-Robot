#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import json
import time

from voice_module import BROADCAST_COMMANDS, VoiceModule, find_uart_ports


def run_demo(port=None, baudrate=115200, init=True,
             listen_seconds=30.0, ignore_zero=True):
    report = {
        "demo": "voice_module_demo",
        "ports": find_uart_ports(),
        "selected_port": port,
        "baudrate": baudrate,
        "init": bool(init),
        "listen_seconds": listen_seconds,
        "ignore_zero": bool(ignore_zero),
        "events": [],
    }

    ignore_ids = [0] if ignore_zero else []
    module = VoiceModule(port=port, baudrate=baudrate)
    try:
        opened = module.open()
        report["opened"] = opened
        print("Voice module opened: {0}".format(json.dumps(opened, ensure_ascii=False)))

        if init:
            event = module.speak("init")
            report["events"].append({"type": "speak", "result": event})
            print("Sent init broadcast: {0}".format(event["frame_hex"]))

        deadline = time.time() + float(listen_seconds)
        print("Listening for voice command frames...")
        while time.time() < deadline:
            frame = module.read_command(timeout_seconds=0.2, ignore_ids=ignore_ids)
            if frame is None:
                continue
            event = {
                "type": "recognition",
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "frame": frame,
            }
            report["events"].append(event)
            print("Read_ID: {0} raw={1} name={2}".format(
                frame.get("command_id"),
                frame.get("raw_hex"),
                frame.get("command_name"),
            ))
            if frame.get("command_word"):
                print("Command word: {0}".format(frame.get("command_word")))
            if frame.get("project_action"):
                print("Project action: {0}".format(frame.get("project_action")))
    finally:
        module.close()

    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default=None)
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--listen-seconds", type=float, default=30.0)
    parser.add_argument("--skip-init", action="store_true")
    parser.add_argument("--show-commands", action="store_true")
    parser.add_argument("--no-ignore-zero", action="store_true")
    args = parser.parse_args(argv)

    if args.show_commands:
        print(json.dumps(BROADCAST_COMMANDS, ensure_ascii=False, indent=2))

    report = run_demo(
        port=args.port,
        baudrate=args.baudrate,
        init=(not args.skip_init),
        listen_seconds=args.listen_seconds,
        ignore_zero=(not args.no_ignore_zero),
    )
    print("Report:")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
