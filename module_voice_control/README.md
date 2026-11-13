# Voice Control Tool

这个模块用于 Yahboom AI 语音模块的独立测试，暂时不接入智能体主流程。

功能：

- 监听语音识别串口帧
- 将厂家固定命令词映射为项目动作
- 按风险等级发送固定播报词
- 输出 JSON/TXT 测试报告

## 连接

语音模块通过 Type-C 接入 Jetson，通常会出现：

```bash
ls /dev/ttyUSB*
```

默认串口参数：

```text
/dev/ttyUSB0
115200
```

模块会自动搜索 `/dev/ttyUSB*` 和 `/dev/ttyACM*`。

## 启动巡检命令

当前不刷固件，复用厂家内置命令词：

```text
你好小亚       唤醒
小车前进       触发 start_inspection
导航去一号位   也触发 start_inspection
停车 / 小车停车 stop
报警           manual_alarm
```

监听到 `start_inspection` 后，报告里的：

```json
{"triggered": true, "action": "start_inspection"}
```

下一步接入智能体时，就用这个字段触发巡检流程。

## 固定播报

厂家模块不能播任意大模型文本，只能播固定短句。本项目先做风险等级映射：

```text
normal   -> 识别到绿色
warning  -> 识别到黄色
abnormal -> 识别到红色
```

这和灯光风险等级一致，现场展示时足够直观。

## 测试顺序

1. 先 dry-run，不需要接模块：

```bash
python3 voice_control_tool.py --dry-run --risk-level abnormal
```

2. 测试播报，不监听命令：

```bash
python3 voice_control_tool.py --broadcast-only --risk-level abnormal
```

3. 测试语音触发：

```bash
python3 voice_control_tool.py --listen-seconds 30
```

然后说：

```text
你好小亚
小车前进
```

4. 同时测试准备播报和监听：

```bash
python3 voice_control_tool.py --ready-broadcast --listen-seconds 30
```

## 输出

默认输出目录：

```text
voice_control_output/
```

其中包括：

```text
voice_control_report.json
voice_control_report.txt
```

