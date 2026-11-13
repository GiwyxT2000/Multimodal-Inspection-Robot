# Camera Capture Tool

这是模块化设计中的相机拍照工具。

它只负责：

- 可选云台归正
- 初始化 Jetbot 相机
- 丢弃预热帧
- 连续采样多帧
- 计算每帧清晰度
- 保存最清晰图片
- 输出 JSON/TXT 报告

它不负责：

- 小车运动
- 二维码识别
- 多模态模型调用
- 智能体规划

## Notebook

打开：

```text
camera_capture_tool.ipynb
```

运行后会输出：

```text
camera_capture_output/test_capture_best.jpg
camera_capture_output/camera_capture_report.json
camera_capture_output/camera_capture_report.txt
```

## 命令行

```bash
python3 camera_capture_tool.py --filename-prefix test_capture
```

如果希望保存全部采样帧：

```bash
python3 camera_capture_tool.py --save-all-samples
```

## 给其他模块调用

```python
from camera_capture_tool import capture_stable_image

result = capture_stable_image(
    camera,
    output_dir="some_output",
    filename_prefix="frame",
    sample_count=5,
)

image_path = result["image_path"]
```

返回结果中包含：

- `image_path`
- `selected_sample`
- `samples`
- `sharpness`
