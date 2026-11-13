# Jetbot 初始化 + 系统自检脚本说明

## 文件

- `jetbot_init_and_selfcheck.py`：终端运行版本。
- `jetbot_init_and_selfcheck.ipynb`：Jupyter Notebook 版本。

## 功能

运行后会依次完成：

1. 使用 Yahboom 默认公开 sudo 密码 `yahboom`。
2. 临时停止官方服务 `jetbot_start`。
3. 重启相机服务 `nvargus-daemon`。
4. 检查服务状态。
5. 检查网络连接。
6. 检查 Robot API。
7. 检查 Camera API 并保存一张测试照片。
8. 保存 JSON/TXT 自检报告。

密码写在脚本中，方便一键初始化；运行报告中不会保存密码。

## 终端运行

```bash
python3 jetbot_init_and_selfcheck.py
```

默认不会让小车运动。若确实需要运动测试：

```bash
python3 jetbot_init_and_selfcheck.py --motion-test
```

运动测试前必须确认小车前方安全或履带架空。

## Jupyter 运行

打开：

```text
jetbot_init_and_selfcheck.ipynb
```

按顺序运行所有单元格即可，不需要手动输入密码。

默认配置：

```python
RUN_INITIALIZATION = True
MOTION_TEST = False
```

## 输出文件

运行后生成：

```text
jetbot_init_selfcheck_report.json
jetbot_init_selfcheck_report.txt
init_selfcheck_frame.jpg
```

## 关于官方服务

脚本执行：

```bash
sudo systemctl stop jetbot_start
```

这只是临时停止官方 APP 控制服务，方便我们自定义程序接管 Robot/Camera。它不会永久禁用服务。

如果后续想恢复官方 APP 控制，可以运行：

```bash
sudo systemctl start jetbot_start
```

或直接重启 Jetbot。
