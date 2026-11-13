# Jetbot 代码目录

## `jetbot_system_check.py`

Jetbot 端系统自检脚本，用于检查：

- Python 环境。
- `jetbot_start`、`nvargus-daemon`、`jetbot_jupyter` 服务状态。
- `/dev/video*` 摄像头设备。
- 外网访问。
- 官方 `Robot` 接口。
- 官方 `Camera` 接口。
- 关键驱动/Notebook 文件。

默认不会让小车运动。

运行：

```bash
python3 jetbot_system_check.py
```

可选短时运动测试：

```bash
python3 jetbot_system_check.py --motion-test
```

运动测试前必须架空履带或清空周围区域。

## `jetbot_system_check.ipynb`

Notebook 版系统自检，适合在 Jetbot 的 Jupyter 中直接打开后 Run All。

默认不会让小车运动，会检查 Robot、Camera、网络、服务状态并生成：

- `jetbot_selfcheck_report.json`
- `jetbot_selfcheck_report.txt`
- `selfcheck_frame.jpg`

如果相机检查失败，Notebook 会自动重启一次 `nvargus-daemon` 并重试。若仍失败，关闭其他相机相关 Notebook/kernel 后，在终端执行 `sudo systemctl restart nvargus-daemon`，再重启当前 kernel。

## `oled_battery_status.py` / `oled_battery_status.ipynb`

OLED 电池状态显示工具。默认只刷新一次 OLED，不会无限循环。

运行脚本：

```bash
python3 oled_battery_status.py
```

循环刷新：

```bash
python3 oled_battery_status.py --loop
```

Notebook 版可直接在 Jetbot Jupyter 中 Run All。

## `oled_debug_test.ipynb`

OLED 最小调试 Notebook。用于判断 OLED 写屏是否生效：

- 检查可能占用 OLED 的服务/进程。
- 临时停止 `jetbot_start`。
- 清空 OLED。
- 写入 `OLED TEST` 和 `BAT:B:L`。
- 如无变化，执行 I2C 扫描，检查是否能看到 `0x3c`。
