# Static OpenCV QR Detector

这个模块只测试静态二维码识别稳定性。

它不做三件事：

- 不移动小车
- 不调用多模态大模型
- 不执行任务规划

它只做：

- 初始化云台到标定正前方
- 初始化相机
- 连续采样多张图片
- 使用 OpenCV `QRCodeDetector` 和多种图像预处理变体解码二维码
- 输出识别率、目标确认率、最佳样本、每帧清晰度和二维码宽度

## Notebook

打开：

```text
qr_static_detector.ipynb
```

先手动把小车放到某个距离，例如 100cm，然后设置：

```python
DISTANCE_LABEL = "100cm"
```

运行后看：

```text
Decoded samples
Target samples
Decode rate
Target rate
Best QR width px
```

## 命令行

```bash
python3 qr_static_detector.py --distance-label 100cm --sample-count 12
```

如果相机被占用，可以先关闭其他 Notebook kernel，再运行。

## 建议实验表

建议每个距离至少测一次：

```text
150cm
120cm
100cm
80cm
60cm
50cm
```

每次记录：

- `target_rate`
- `best_detection.qr_width_px`
- 失败样本对应的 `sharpness`
- 标注图中二维码是否肉眼可见

这一步的目标是得到一个结论：OpenCV QR 在多远以内可以稳定作为“身份确认工具”。
