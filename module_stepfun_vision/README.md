# StepFun 多模态视觉识别模块

这个模块只做一件事：读取一张本地图片，调用 StepFun `step-3.7-flash` 多模态模型，并保存结构化识别报告。

它不控制小车、不初始化相机、不识别二维码、不控制云台。建议先用 `module_camera_capture` 拍出稳定图片，再把图片交给本模块分析。

## API Key 放置方式

任选一种：

1. 终端环境变量：

```bash
export STEPFUN_API_KEY="你的API Key"
```

2. 在当前运行目录创建文本文件：

```text
stepfun_api_key.txt
```

文件内容只放 API Key 本身。

3. 在 Notebook 里传入：

```python
API_KEY = "你的API Key"
```

## 命令行运行

假设已经用相机模块拍好了图片：

```bash
python3 stepfun_vision_tool.py ../module_camera_capture/camera_capture_output/test_capture_best.jpg
```

输出文件默认在：

```text
stepfun_vision_output/stepfun_vision_report.json
stepfun_vision_output/stepfun_vision_report.txt
```

## 输出字段

模型会被要求只输出 JSON，主要字段包括：

- `sign_visible`：是否看到标牌
- `sign_type`：`anchor`、`inspection`、`unknown` 或 `none`
- `station_guess`：例如 `A01`
- `main_text`：可见主要文字
- `scene_summary`：画面概括
- `observations`：关键观察
- `risk_level`：`normal`、`warning` 或 `abnormal`
- `risk_reason`：风险依据
- `next_action`：下一步建议
- `confidence`：置信度

## 推荐测试顺序

1. 先运行 `module_camera_capture/camera_capture_tool.ipynb`，确认图片清晰。
2. 修改本模块 Notebook 的 `IMAGE_PATH` 指向刚拍的图片。
3. 运行本模块，看 `Parse OK` 是否为 `True`。
4. 打开 `stepfun_vision_report.txt`，检查模型是否正确理解标牌、场景和风险等级。

## 当前定位

这是后续智能体的“视觉理解工具”。等它稳定后，综合智能体只需要调用：

```python
from stepfun_vision_tool import run_demo
```

然后读取报告里的 `parsed` 字段即可。
