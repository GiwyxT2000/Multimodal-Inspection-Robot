# 声光反馈工具模块

这个模块只负责风险等级的声光反馈：

- 蜂鸣器
- RGB 灯带流动
- RGB 灯带五次闪烁

它不移动小车，不调用相机、云台、二维码识别或多模态模型。

## 风险等级映射

```text
normal   -> 绿灯 + 1 声蜂鸣
warning  -> 黄灯 + 2 声蜂鸣
abnormal -> 红灯 + 3 声蜂鸣
```

RGB 效果为：

```text
对应颜色流动 -> 全灯带闪烁五次 -> 关闭
```

## Notebook 运行

打开：

```text
inspection_feedback_tool.ipynb
```

手动测试：

```python
RISK_LEVEL = "abnormal"
SEARCH_REPORT_PATH = None
```

从目标搜索报告读取：

```python
SEARCH_REPORT_PATH = "../module_target_search/target_search_output/target_search_report.json"
```

如果设置了 `SEARCH_REPORT_PATH`，会优先使用报告中的 `risk_level`。

## 命令行运行

```bash
python3 inspection_feedback_tool.py --risk-level abnormal
```

只测试 RGB：

```bash
python3 inspection_feedback_tool.py --risk-level warning --no-buzzer
```

只测试蜂鸣器：

```bash
python3 inspection_feedback_tool.py --risk-level normal --no-rgb
```

## 与其他模块的关系

最终编排器中，推荐顺序是：

```text
目标搜索工具 -> 小车运动工具 -> 声光反馈工具
```

也就是：

```python
best_pose = search_report["vision"]["parsed"]["best_pose"]
risk_level = search_report["vision"]["parsed"]["risk_level"]

motion_tool.run_demo(best_pose=best_pose, enable_motion=True)
feedback_tool.run_demo(risk_level=risk_level)
```

这样车身朝向和声光提示保持解耦，便于单独调试。
