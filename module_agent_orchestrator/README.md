# 智能体编排器模块

这个模块负责把前面已经测试过的工具串成一个完整巡检流程：

```text
接收巡检指令
-> 直线靠近 A01 工位定位牌并停车
-> 云台搜索工业工况巡检牌
-> 小车底盘转向工况牌方向
-> 按风险等级触发蜂鸣器和 RGB 灯带
```

它不重新实现底层能力，而是调用：

```text
qr_anchor_approach_demo.py
module_target_search/target_search_tool.py
module_motion_tool/robot_motion_tool.py
module_feedback_tool/inspection_feedback_tool.py
```

## 当前锚点阶段说明

第一版编排器中，锚点停车阶段调用现有 OpenCV QR 靠近工具：

```text
anchor_strategy = "opencv_qr"
```

也就是说，目前不是最终设想中的“远处大模型 + 近处 OpenCV”混合锚点控制。这个混合策略后续可以作为新的锚点工具替换进编排器，其他搜索、转向、反馈模块不需要改。

当前锚点靠近已经采用分阶段步进：

```text
前 3 段：正常直线靠近
第 4 段以后：缩短粗步长，避免冲过头
QR 接近阈值后：micro 小步靠近
```

默认参数偏保守，目标是在约 40cm 左右停车，给后续云台搜索留下视野余量。如果仍然太近，优先继续降低：

```python
anchor_micro_step_duration
anchor_fine_step_duration
anchor_late_step_duration
```

如果已经明显跑过头，可以临时打开可选后退：

```python
anchor_enable_backoff=True
```

## 安全测试

第一次建议：

```python
ENABLE_MOTION = False
```

此时：

- 锚点靠近阶段不会真正移动。
- 车身转向阶段不会真正移动。
- 云台搜索会执行。
- 声光反馈会执行。

如果想先跳过锚点靠近，只测试后半段：

```python
RUN_ANCHOR = False
```

完整真实运动联调时再设置：

```python
ENABLE_MOTION = True
RUN_ANCHOR = True
```

## 输出

主报告：

```text
inspection_agent_output/inspection_agent_report.json
inspection_agent_output/inspection_agent_report.txt
```

子阶段报告：

```text
01_anchor_approach/
02_target_search/
03_body_motion/
04_feedback/
```

主报告里的 `decision` 会汇总关键结果：

```python
{
  "target_found": true,
  "best_pose": "left_wide",
  "risk_level": "abnormal",
  "inspection_summary": "...",
  "next_action": "..."
}
```

## 推荐测试顺序

1. `RUN_ANCHOR=False, ENABLE_MOTION=False`：测试搜索、风险判断、声光反馈。
2. `RUN_ANCHOR=False, ENABLE_MOTION=True`：测试搜索后车身转向和声光反馈。
3. `RUN_ANCHOR=True, ENABLE_MOTION=False`：测试锚点阶段 dry run + 后续流程。
4. `RUN_ANCHOR=True, ENABLE_MOTION=True`：完整联调。
