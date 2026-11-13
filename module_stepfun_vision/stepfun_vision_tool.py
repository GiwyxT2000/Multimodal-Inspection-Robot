#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StepFun multimodal vision tool.

This module only sends one local image to a multimodal model and saves a
structured report. It does not move the robot, read QR codes, or control the
camera/gimbal. Use it after module_camera_capture has produced a stable image.
"""

from __future__ import print_function

import argparse
import base64
import codecs
import json
import mimetypes
import os
import time
import traceback
import urllib.request


DEFAULT_MODEL = "step-3.7-flash"
DEFAULT_ENDPOINT = "https://api.stepfun.com/v1/chat/completions"
DEFAULT_OUTPUT_DIR = "stepfun_vision_output"
DEFAULT_TASK_PROMPT = (
    "请分析这张巡检图像。判断画面中是否存在工位定位牌或工业工况巡检牌，"
    "读取可见文字，识别明显设备状态或安全风险，并给出简短处置建议。"
)
DEFAULT_SYSTEM_PROMPT = (
    "你是一个部署在Jetbot巡检小车上的工业视觉分析模块。"
    "你只根据输入图像回答，不要编造看不见的信息。"
    "必须只输出一个JSON对象，不能输出Markdown、解释文字或代码块。"
)
DEFAULT_JSON_SCHEMA_PROMPT = """
请严格输出以下JSON字段：
{
  "sign_visible": true或false,
  "sign_type": "anchor"、"inspection"、"unknown"或"none",
  "station_guess": "A01"或null,
  "main_text": "画面中最重要的可见文字，无法确认则为空字符串",
  "scene_summary": "一句话概括画面",
  "observations": ["关键观察1", "关键观察2"],
  "risk_level": "normal"、"warning"或"abnormal",
  "risk_reason": "风险等级依据",
  "next_action": "建议下一步动作",
  "confidence": 0到1之间的数字
}
""".strip()


def now_string():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def ensure_dir(path):
    if path and not os.path.exists(path):
        os.makedirs(path)


def write_json(path, data):
    with codecs.open(path, "w", "utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_text(path, text):
    with codecs.open(path, "w", "utf-8") as f:
        f.write(text)


def read_api_key(explicit_key=None, key_file=None):
    if explicit_key:
        return explicit_key.strip()

    for name in ["STEPFUN_API_KEY", "STEP_API_KEY"]:
        value = os.environ.get(name)
        if value:
            return value.strip()

    filenames = []
    if key_file:
        filenames.append(key_file)
    filenames.extend(["stepfun_api_key.txt", "step_api_key.txt"])

    for filename in filenames:
        if filename and os.path.exists(filename):
            with codecs.open(filename, "r", "utf-8") as f:
                value = f.read().strip()
                if value:
                    return value
    return ""


def guess_mime_type(path):
    mime_type, _ = mimetypes.guess_type(path)
    if mime_type:
        return mime_type
    lower = path.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def image_to_data_url(path):
    if not os.path.exists(path):
        raise RuntimeError("Image file does not exist: {0}".format(path))
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return "data:{0};base64,{1}".format(guess_mime_type(path), encoded)


def strip_json_fence(text):
    if text is None:
        return ""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def extract_json(text):
    text = strip_json_fence(text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("VLM JSON is not an object.")
    except ValueError:
        raise
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(text[start:end + 1])
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("VLM JSON is not an object.")
    raise ValueError("No JSON object found in VLM response.")


class StepFunVisionClient(object):
    def __init__(self, api_key=None, key_file=None, model=DEFAULT_MODEL,
                 endpoint=DEFAULT_ENDPOINT, timeout=90,
                 reasoning_effort="low"):
        self.api_key = read_api_key(api_key, key_file=key_file)
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout
        self.reasoning_effort = reasoning_effort
        if not self.api_key:
            raise RuntimeError(
                "Missing API key. Set STEPFUN_API_KEY, create "
                "stepfun_api_key.txt, or pass api_key explicitly."
            )

    def chat(self, messages, temperature=0.0, max_tokens=1000):
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        message = data["choices"][0]["message"]
        content = message.get("content", "")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(item.get("text", ""))
                else:
                    parts.append(str(item))
            content = "\n".join(parts)
        return content, data


def analyze_image(image_path,
                  task_prompt=DEFAULT_TASK_PROMPT,
                  api_key=None,
                  key_file=None,
                  model=DEFAULT_MODEL,
                  endpoint=DEFAULT_ENDPOINT,
                  timeout=90,
                  reasoning_effort="low",
                  temperature=0.0,
                  max_tokens=1000):
    client = StepFunVisionClient(
        api_key=api_key,
        key_file=key_file,
        model=model,
        endpoint=endpoint,
        timeout=timeout,
        reasoning_effort=reasoning_effort,
    )
    user_text = task_prompt.strip() + "\n\n" + DEFAULT_JSON_SCHEMA_PROMPT
    messages = [
        {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}},
            ],
        },
    ]

    text, raw = client.chat(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    result = {
        "image_path": image_path,
        "text": text,
        "parsed": {},
        "parse_ok": False,
        "parse_error": None,
    }
    try:
        result["parsed"] = extract_json(text)
        result["parse_ok"] = True
    except Exception as exc:
        result["parse_error"] = repr(exc)
    result["raw_response"] = raw
    return result


def write_text_report(report, path):
    vision = report.get("vision") or {}
    lines = []
    lines.append("StepFun Vision Tool")
    lines.append("Time: {0} -> {1}".format(report.get("started_at"), report.get("finished_at")))
    lines.append("Summary: {0}".format(report.get("summary")))
    lines.append("")
    lines.append("== Config ==")
    lines.append(json.dumps(report.get("config", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Parsed Result ==")
    lines.append(json.dumps(vision.get("parsed", {}), ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("== Raw Text ==")
    lines.append(vision.get("text") or "")
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
    lines.append("StepFun Vision Tool")
    lines.append("Summary: {0}".format(report.get("summary")))
    lines.append("Parse OK: {0}".format(vision.get("parse_ok")))
    lines.append("Sign visible: {0}".format(parsed.get("sign_visible")))
    lines.append("Sign type: {0}".format(parsed.get("sign_type")))
    lines.append("Risk level: {0}".format(parsed.get("risk_level")))
    lines.append("JSON report: {0}".format(report.get("report_json")))
    lines.append("Text report: {0}".format(report.get("report_txt")))
    return "\n".join(lines)


def run_demo(image_path,
             output_dir=DEFAULT_OUTPUT_DIR,
             task_prompt=DEFAULT_TASK_PROMPT,
             api_key=None,
             key_file=None,
             model=DEFAULT_MODEL,
             endpoint=DEFAULT_ENDPOINT,
             timeout=90,
             reasoning_effort="low",
             temperature=0.0,
             max_tokens=1000):
    ensure_dir(output_dir)
    started_at = now_string()
    report = {
        "demo": "stepfun_vision_tool",
        "started_at": started_at,
        "finished_at": None,
        "summary": "running",
        "config": {
            "image_path": image_path,
            "output_dir": output_dir,
            "task_prompt": task_prompt,
            "model": model,
            "endpoint": endpoint,
            "timeout": timeout,
            "reasoning_effort": reasoning_effort,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        "vision": None,
        "error": None,
        "traceback": None,
    }
    try:
        report["vision"] = analyze_image(
            image_path=image_path,
            task_prompt=task_prompt,
            api_key=api_key,
            key_file=key_file,
            model=model,
            endpoint=endpoint,
            timeout=timeout,
            reasoning_effort=reasoning_effort,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if report["vision"].get("parse_ok"):
            report["summary"] = "Vision analysis completed."
        else:
            report["summary"] = "Vision analysis completed, but JSON parsing failed."
    except Exception as exc:
        report["summary"] = "Error: {0}".format(repr(exc))
        report["error"] = repr(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        report["finished_at"] = now_string()

    json_path = os.path.join(output_dir, "stepfun_vision_report.json")
    text_path = os.path.join(output_dir, "stepfun_vision_report.txt")
    report["report_json"] = json_path
    report["report_txt"] = text_path
    write_json(json_path, report)
    write_text_report(report, text_path)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("image_path")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--task-prompt", default=DEFAULT_TASK_PROMPT)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--key-file", default=None)
    parser.add_argument("--model", default=os.environ.get("STEPFUN_VL_MODEL", DEFAULT_MODEL))
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--reasoning-effort", default="low")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=1000)
    args = parser.parse_args(argv)

    report = run_demo(
        image_path=args.image_path,
        output_dir=args.output_dir,
        task_prompt=args.task_prompt,
        api_key=args.api_key,
        key_file=args.key_file,
        model=args.model,
        endpoint=args.endpoint,
        timeout=args.timeout,
        reasoning_effort=args.reasoning_effort,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    print(summarize_report(report))
    return 0 if not report.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
