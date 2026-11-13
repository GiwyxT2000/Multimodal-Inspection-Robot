# QR Anchor Approach Demo

这个脚本用于测试“工位定位锚点牌”的二维码定位停车能力。

## 新版改动

- 启动后会先把云台归正到标定位置：
  - `HOME_PAN = 2048`
  - `HOME_TILT = 2868`
- 移动策略改为两段式：
  - 远距离：粗步前进，默认 `speed=0.55, duration=0.90`
  - 接近后：细步前进，默认 `speed=0.42, duration=0.40`
- 二维码宽度达到停车阈值的 55% 后自动切换细步。
- 每次前进前加入短启动脉冲，默认 `kick_speed=0.75, kick_duration=0.12`，用于克服电机/履带启动门槛。
- 每次前进停止后增加稳定等待，默认 `post_stop_settle=0.90` 秒，避免云台颤动时立即拍照。
- 每次观察会先丢弃 2 帧，再连续采集 5 帧，并记录每帧 `sharpness`，优先选择已解码且更清晰的图像。

## 功能

```text
云台归正
-> Jetbot 相机初始化
-> 保存 camera_init_frame.jpg 预热图
-> OpenCV QRCodeDetector 解码定位牌二维码
-> 判断 role=stop_anchor, station=A01
-> 二维码太小：粗步前进
-> 二维码接近阈值：细步前进
-> 二维码达到阈值：停车
-> 保存每一步图片、标注图和报告
```

## 摆放建议

- 只放 `A01_工位定位锚点牌`，先不要放巡检目标标牌。
- 标牌竖直，正面朝向小车。
- 小车与标牌初始距离可以从 150 cm 到 200 cm 开始。
- 第一轮尽量让标牌在画面正前方。
- 前方路径至少留出 2 m 安全距离。
- 手放在电源开关附近，发现异常立即断电。

## 推荐运行

在 Jetbot 的 `Notebook/the21thYDS` 目录运行：

```bash
python3 qr_anchor_approach_demo.py
```

如果想先不动小车，只测试二维码识别和云台归正：

```bash
python3 qr_anchor_approach_demo.py --no-motion
```

如果 640x480 相机初始化失败，可以退回：

```bash
python3 qr_anchor_approach_demo.py --camera-width 224 --camera-height 224
```

## 关键参数

- `--home-pan 2048 --home-tilt 2868`
  - 云台归正位置。不要轻易改小 `home-tilt`，之前低值会触发机械限位异响。

- `--stop-width-ratio 0.12`
  - 停车阈值，默认二维码宽度达到画面宽度的 12% 就停车。
  - 640 宽度时约等于 77 px。

- `--step-speed 0.55 --step-duration 0.90`
  - 远距离粗步参数。

- `--fine-step-speed 0.42 --fine-step-duration 0.40`
  - 接近二维码后的细步参数。

- `--motor-kick-speed 0.75 --motor-kick-duration 0.12`
  - 每一步前的短启动脉冲。如果脚本显示移动但小车几乎不动，优先调大这两个参数或粗步参数。

- `--fine-width-ratio 0.55`
  - 二维码宽度达到停车阈值的 55% 后切换细步。

- `--max-steps 16`
  - 最大前进脉冲次数。

- `--max-missing-steps 10`
  - 连续多次找不到定位牌时停止，避免盲目前进太久。
- `--post-stop-settle 0.90`
  - 每次小车停止后等待云台和车身稳定，再进入下一轮拍照。
- `--frames-per-step 5 --capture-warmup-frames 2 --capture-sample-interval 0.12`
  - 每轮观察丢弃预热帧后多帧采样，用于降低单张糊图导致二维码识别失败的概率。
- `--pre-capture-settle 0.20`
  - 每轮正式采样前额外等待，适合云台刚归正或地面不平时使用。

## 调参建议

如果从 2 米外仍然几乎不动：

```bash
python3 qr_anchor_approach_demo.py --step-speed 0.65 --step-duration 1.00 --motor-kick-speed 0.85 --motor-kick-duration 0.16
```

如果粗步移动太猛：

```bash
python3 qr_anchor_approach_demo.py --step-duration 0.50
```

如果接近后停车还是太远：

```bash
python3 qr_anchor_approach_demo.py --stop-width-ratio 0.14
```

如果接近后停车太近：

```bash
python3 qr_anchor_approach_demo.py --stop-width-ratio 0.10
```

如果最后一两步冲得太多：

```bash
python3 qr_anchor_approach_demo.py --fine-step-duration 0.20
```

## 输出

默认输出目录：

```text
qr_anchor_approach_output/
```

包含：

```text
camera_init_frame.jpg
camera_init_frame_annotated.jpg
step_000.jpg
step_000_annotated.jpg
...
qr_anchor_approach_report.json
qr_anchor_approach_report.txt
```

标注图会画出二维码边框，并显示 role、station 和二维码像素宽度。

建议先看 `camera_init_frame_annotated.jpg`：

- 如果这里已经能看到绿色二维码框，说明相机初始化和二维码检测都正常。
- 如果这里没有二维码框，先调整标牌位置、距离、光照或云台角度，再让小车移动。
