# 编排器参数设置说明

编排器默认不覆盖各工具模块的默认参数。

也就是说，全流程运行时：

- 锚点靠近参数来自 `qr_anchor_approach_demo.py`
- 云台搜索参数来自 `module_target_search/target_search_tool.py`
- 小车转向参数来自 `module_motion_tool/robot_motion_tool.py`
- 声光反馈参数来自 `module_feedback_tool/inspection_feedback_tool.py`

编排器只负责把模块串起来，并传递必要信息，例如：

```python
enable_motion
best_pose
risk_level
output_dir
```

## 修改默认参数

如果某个模块的参数已经调好，请直接改对应模块自己的默认值。

例如，修改小车转向角度：

```text
module_motion_tool/robot_motion_tool.py
```

修改：

```python
DEFAULT_TURN_DURATION
DEFAULT_TURN_SPEED
DEFAULT_KICK_DURATION
```

修改灯光闪烁次数：

```text
module_feedback_tool/inspection_feedback_tool.py
```

修改：

```python
DEFAULT_RGB_BLINK_COUNT
DEFAULT_RGB_LOOPS
```

修改锚点停车步长：

```text
qr_anchor_approach_demo.py
```

修改：

```python
DEFAULT_FINE_STEP_DURATION
DEFAULT_MICRO_STEP_DURATION
DEFAULT_LATE_STEP_DURATION
```

## 临时覆盖参数

如果只想某次全流程临时覆盖参数，可以在编排器 Notebook 的 `run_demo(...)` 中显式传入。

例如：

```python
report = run_demo(
    enable_motion=True,
    motion_turn_duration=0.20,
    feedback_rgb_blink_count=5,
)
```

只要不传这些参数，编排器就不会覆盖模块默认值。
