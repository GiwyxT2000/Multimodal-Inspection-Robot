# Jetbot 工业巡检控制台

这是比赛展示用的前端控制台。页面不再只是读取报告，而是通过一个轻量 Python 后端启动巡检流程，并在巡检中/巡检完成后展示阶段状态和最终报告。

## 功能

- 左侧一键“启动巡检”
- 可选择是否允许小车运动
- 巡检中自动刷新阶段状态
- 巡检完成后自动展示：
  - QR 定位阶段状态和成功识别图片
  - 工况牌搜索图片
  - 多模态大模型识别结果
  - 大模型处置建议
  - 最终警报判断：正常 / 预警 / 警报
- 支持手动选择历史 `inspection_agent_report.json`

## 启动方式

在 Jetbot 上运行：

```bash
cd /home/jetbot/Notebook/the21thYDS/module_web_dashboard
python3 dashboard_server.py --host 0.0.0.0 --port 8060
```

然后在电脑浏览器打开：

```text
http://<jetbot-ip>:8060
```

例如：

```text
http://192.168.43.123:8060
```

## 页面使用

1. 确认场地安全。
2. 保持“允许小车运动”勾选。
3. 点击“启动巡检”。
4. 页面自动轮询状态。
5. 流程完成后查看警报判断、识别结果和处置建议。

如果只想演示页面，不想让小车动，取消“允许小车运动”后点击启动。

## 后端调用的主流程

后端调用：

```python
module_agent_orchestrator.inspection_agent_orchestrator.run_demo(
    output_dir="module_agent_orchestrator/inspection_agent_output",
    command="开始 A01 工位巡检",
    enable_motion=True,
)
```

也就是说，底层仍然复用已经调好的模块化智能体流程。

