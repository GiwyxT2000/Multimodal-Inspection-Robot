# 小车运动工具模块

这个模块只负责 Jetbot 底盘运动：

- 前进
- 后退
- 原地左转
- 原地右转
- 根据 `best_pose` 做车身微转

它不调用相机、云台、二维码识别、多模态模型、蜂鸣器或 RGB 灯带。

## 为什么单独拆出来

目标搜索模块输出的 `best_pose` 表示目标牌相对小车的方向，例如：

```text
center
left
right
left_wide
right_wide
```

云台扫描结束后应该回正，避免影响下一次实验。若需要让小车正面朝向目标牌，应由本模块控制底盘原地微转，而不是让云台停在 `best_pose`。

## best_pose 映射

```text
center / none -> 不转
left / left_wide -> 小车左转
right / right_wide -> 小车右转
```

## 安全开关

默认不真正运动：

```python
ENABLE_MOTION = False
```

需要确认场地安全后再改为：

```python
ENABLE_MOTION = True
```

命令行也一样，必须显式添加：

```bash
python3 robot_motion_tool.py --action align --best-pose right_wide --enable-motion
```

## 推荐测试顺序

1. `ENABLE_MOTION = False`，测试 `best_pose=right_wide`，确认报告里映射为右转。
2. 清空车身周围障碍物。
3. `ENABLE_MOTION = True`，测试右转微动。
4. 根据实际幅度调整：

```python
TURN_SPEED = 0.45
TURN_DURATION = 0.80
KICK_SPEED = 0.75
KICK_DURATION = 0.08
```

如果转动过大，优先降低 `TURN_DURATION`；如果不动，略微提高 `KICK_DURATION` 或 `KICK_SPEED`。

## 与后续模块的关系

最终智能体编排器会这样使用：

```python
best_pose = search_report["vision"]["parsed"]["best_pose"]
risk_level = search_report["vision"]["parsed"]["risk_level"]

motion_report = motion.run_demo(best_pose=best_pose, enable_motion=True)
feedback_report = feedback.run_demo(risk_level=risk_level)
```
