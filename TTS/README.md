# Yahboom AI Voice Module Notes

The stock firmware uses fixed command words and fixed broadcast phrases.
It does not accept arbitrary Chinese text as TTS.

## UART

Default UART:

```text
/dev/ttyUSB0
baudrate 115200
```

Vendor protocol:

```text
Broadcast:   AA 55 FF <broadcast_id> FB
Recognition: AA 55 <function_id> <command_id> FB
```

The demo parser uses the fourth byte as `command_id`, matching the vendor
example where saying "关灯" returns `Read_ID: 10`.

## Project Mapping

The spreadsheet `命令词播报词协议列表V3_中文.xlsx` contains 110 protocol rows:

```text
1-10    function/wake words
11-82   active command words
83-110  passive broadcast phrases
```

For the first competition demo, use the stock command words:

```text
你好，小亚      wake module
小车前进        start_patrol, Read_ID=4
停车 / 小车停止 stop, Read_ID=1 or 2
小车休眠        sleep, Read_ID=3
```

This avoids custom firmware while still demonstrating voice-triggered agent
execution.

## Test

```bash
cd /home/jetbot/Notebook/the21thYDS/TTS
python3 voice_module_demo.py
```

Expected output after saying "小车前进":

```text
Read_ID: 4 raw=aa550004fb name=car_forward
Command word: 小车前进
Project action: start_patrol
```

## Passive Broadcast

The module still cannot speak arbitrary LLM-generated Chinese text. It can only
play fixed passive broadcast phrases from the spreadsheet, for example:

```python
module.speak("init")       # vendor UART sample, sends AA 55 FF 67 FB
module.speak("init_xlsx")  # spreadsheet phrase 初始化完成, sends AA 55 FF 58 FB
module.speak("识别到红色")
module.speak("放置完成")
```

For the competition demo, use the module for voice commands and short fixed
status feedback. Show the full multimodal inspection report on screen.
