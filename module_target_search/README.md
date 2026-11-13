# 工况牌目标搜索模块

这个模块用于测试：

```text
云台预设视角扫描 -> 每个视角稳定拍照 -> StepFun 多模态模型选择最佳视角
```

它不移动小车底盘，也不触发蜂鸣器/RGB灯带。它的输出会作为后续综合智能体和反馈模块的输入。

扫描结束后，云台默认回到正视位置，避免下一次重复实验时 `center` 受到上一次 `best_pose` 的影响。`best_pose` 只表示目标相对方位，不表示云台最终停留位置。

注意：`left/right` 命名表示目标相对小车车身的方向，而不是舵机控制值的正负方向。当前实测云台中，较大的 pan 值会看到小车左侧，因此代码已在 `pose_table()` 中做了左右映射修正。

## 运行前提

1. 相机服务正常。
2. 云台正视参数已经校准：

```python
HOME_PAN = 2048
HOME_TILT = 2868
```

3. 已配置 StepFun API Key，任选一种方式：

```bash
export STEPFUN_API_KEY="你的API Key"
```

或者在当前目录放：

```text
stepfun_api_key.txt
```

## Notebook 运行

打开：

```text
target_search_tool.ipynb
```

默认参数：

```python
SEARCH_PROFILE = "front_sign_wide"
PAN_DELTA = 620
TILT_UP_DELTA = 120
TILT_DOWN_DELTA = 260
MAX_TOKENS = 4096
```

如果左右范围需要收窄，把：

```python
SEARCH_PROFILE = "front_sign"
```

如果目标偏下，可以增大：

```python
TILT_DOWN_DELTA
```

如果目标偏上，可以增大：

```python
TILT_UP_DELTA
```

## 命令行运行

```bash
python3 target_search_tool.py
```

更大左右搜索范围：

```bash
python3 target_search_tool.py --search-profile front_sign_wide
```

## 输出文件

默认输出目录：

```text
target_search_output/
```

关键报告：

```text
target_search_output/target_search_report.json
target_search_output/target_search_report.txt
```

每个视角会保存一张图片，例如：

```text
target_search_output/center_best.jpg
target_search_output/left_best.jpg
target_search_output/right_best.jpg
```

## 关键结果字段

`vision.parsed` 里重点看：

- `target_found`：是否找到工况牌
- `best_pose`：最佳视角，例如 `center`、`left`、`right`、`down`
- `risk_level`：`normal`、`warning` 或 `abnormal`
- `visible_text`：模型读到的文字
- `inspection_summary`：巡检牌信息摘要
- `next_action`：建议处置方案

## 风险分级标准

提示词中已经固定风险分级规则，便于比赛演示和论文描述：

- `normal`：未发现明显异常，仅为正常设备或普通信息提示。
- `warning`：存在轻微隐患、信息不确定、需要人工复核或持续观察。
- `abnormal`：出现明确异常或危险信号，例如过热、高温读数、报警灯亮起、`DANGER`、`OVERHEAT`、漏油、裸露/散乱线缆、电气危险、停机/禁止靠近等。

只要画面或文字中出现明确异常证据之一，模型应优先判定为 `abnormal`。

后续综合智能体可以直接把这些字段传给反馈模块：

```python
best_pose = report["vision"]["parsed"]["best_pose"]
risk_level = report["vision"]["parsed"]["risk_level"]
```

如果需要让小车正面朝向目标牌，应由“小车运动工具”根据 `best_pose` 控制底盘原地微转，而不是让本模块把云台停在 `best_pose`。

## 关于 max_tokens

目标搜索模块属于多模态语义理解阶段，不按底盘控制模块的短指令思路压缩输出。默认：

```python
MAX_TOKENS = 4096
```

这样模型可以充分比较多个云台视角，解释为什么选择某个 `best_pose`，并给出更完整的工况分析和处置建议。

## 推荐测试方法

1. 先把工况牌放在正前方，确认 `best_pose=center`。
2. 把工况牌移动到小车左侧，确认 `best_pose=left` 或 `left_wide`。
3. 把工况牌移动到小车右侧，确认 `best_pose=right` 或 `right_wide`。
4. 如果识别结果稳定，再启用后续反馈模块。
