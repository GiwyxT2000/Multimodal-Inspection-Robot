# QR Anchor Static Test

这个脚本用于把二维码识别从运动控制里拆出来，单独测试不同距离下 OpenCV 是否能解码工位定位牌。

## 使用方式

1. 手动把小车放到某个距离，例如 200 cm、150 cm、120 cm、100 cm、80 cm。
2. 标牌尽量完整出现在画面中，不要只露出一半。
3. 运行 `qr_anchor_static_test.ipynb`。
4. 修改 Notebook 里的 `DISTANCE_LABEL`，每个距离单独生成一个输出目录。

## 推荐距离

```text
200cm
150cm
120cm
100cm
80cm
60cm
```

## 输出

每次运行会生成：

```text
qr_anchor_static_output_100cm/
  sample_000.jpg
  sample_000_annotated.jpg
  ...
  qr_anchor_static_report.json
  qr_anchor_static_report.txt
```

## 判断标准

如果输出中出现：

```text
Target OK: True
Payload: {"station": "A01", "role": "stop_anchor", ...}
```

说明该距离可以识别定位锚点。

如果 `QR width px` 有值但 `Target OK=False`，说明检测到二维码角点或解出了非目标内容。

如果 `QR width px=None`，说明 OpenCV 没有检测到二维码。常见原因：

- 标牌太远，二维码像素太小。
- 标牌没有完整进入画面。
- 画面模糊或运动残影。
- 光照反光。
- 角度倾斜太大。

## 相机初始化

脚本会自动释放旧 `Camera.instance`，并在失败时停止 `jetbot_start`、重启 `nvargus-daemon` 后重试。  
如果仍然失败，通常是其他 Notebook kernel 还占着相机，先关闭那些 kernel 再运行。

## 这次图片的判断

你给的 `step_004_annotated.jpg` 中，标牌只露出左侧一部分，二维码也没有完整出现在画面里，所以 OpenCV 解码失败是正常的。静止测试时要先让完整二维码进入画面，再测试不同距离的识别边界。
