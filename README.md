# 基于多模态云边协同智能体的工业产线巡检机器人

第21届研究生电子设计竞赛 · 人工智能赛道上海赛区**二等奖**获奖作品配套源码。

本仓库是技术论文《基于多模态云边协同智能体的工业产线巡检机器人》的配套代码。系统以 Jetbot（Jetson Nano）为移动执行平台，采用「云端理解、边缘执行」的协同架构，把实时控制与语义理解解耦：边缘端负责二维码工位确认、云台主动扫描、底盘运动与声光语音反馈；云端多模态大模型负责对工业工况巡检牌做端到端语义理解与风险决策。

## 设计思路

- **二维码只做锚点，不编码工况。** 工位定位牌使用短码 `A01_STOP`，由 OpenCV 在近距离完成身份确认与停车判断；设备状态、温度读数、危险标识等真正的工况信息不写进二维码，而是由大模型直接读图理解，更贴近「看设备、读标识、判风险」的真实巡检方式。
- **按实时性划分任务边界。** 相机采集、QR 解码、云台控制、底盘运动、声光报警这类有严格时序要求的任务留在边缘；需要综合推理的语义理解交给云端，规避 Jetson Nano 无法本地部署大模型的算力瓶颈。
- **模块化工具链。** 各功能封装成独立、可单独运行和测试的工具，统一输出标准化 JSON 报告，再由智能体编排器按流程调度。模块之间通过文件与 JSON 交互，松耦合、可替换。

## 巡检闭环

```
工位定位 → 主动搜索 → 多模态理解 → 反馈响应 → 网页展示
```

编排器接收网页端启动指令后，先分段前进靠近 A01 工位，二维码像素宽度达到阈值即停车；随后云台按预设姿态扫描并择优保存多视角图像，交给云端模型选出最佳视角并输出风险等级；再依次触发车身微转朝向目标、RGB 灯带、蜂鸣器与语音播报（normal / warning / abnormal 三级），最后汇总巡检报告，供网页控制台轮询展示。

## 模块

| 目录 | 作用 |
|---|---|
| `module_qr_static_opencv/` | OpenCV 二维码检测与工位身份确认 |
| `module_camera_capture/` | 相机拍照、多帧采样与清晰度择优 |
| `module_target_search/` | 云台主动扫描与工况巡检牌搜索 |
| `module_stepfun_vision/` | 云端 StepFun `step-3.7-flash` 多模态视觉理解 |
| `module_motion_tool/` | 底盘分段前进、停车与车身微转 |
| `module_feedback_tool/` | RGB 灯带与蜂鸣器分级报警 |
| `module_voice_control/` | 固定词语音播报 |
| `module_agent_orchestrator/` | 智能体编排器，串联全流程并汇总巡检报告 |
| `module_web_dashboard/` | 网页控制台，HTTP 轮询展示证据与结论 |

边缘侧另有 `TTS/`（AI 语音模块串口协议与命令词表）、根目录 `qr_anchor_approach_demo.py`（工位靠近）与 `generate_*_sign.py`（定位牌、工况巡检牌生成）等配套脚本。各模块目录下的 `README.md` 有更细的参数与单独调试说明。

## 运行环境

- Jetbot 智能小车（Jetson Nano）、摄像头、二自由度云台、RGB 灯带、蜂鸣器、AI 语音模块
- Python 3，主要依赖 `opencv-python`、`Pillow`、`reportlab`、`pyserial`
- Jetbot 官方 `jetbot` 包（`Robot` / `Camera` 接口）及设备自带的 `RGB_Lib`、`gimbal_scan_demo`、`RPi.GPIO`、`smbus` 等驱动
- 云端模型：阶跃星辰 StepFun `step-3.7-flash` 多模态大模型（需 API Key）

> 部分底层驱动与云台示例来自 Jetbot 出厂环境，不在本仓库内；`new/`、`yunt/` 目录保留了相关的基础例程供对照。网页控制台后端仅用 Python 标准库，前端 `index.html` 为纯静态页面，无需构建。

## 配置

**API Key 不入库。** 运行前任选一种方式提供，仓库里只有占位说明：

```bash
export STEPFUN_API_KEY="你的API Key"
```

或在运行目录放一个 `stepfun_api_key.txt`（内容只写 Key 本身），也可通过 `--api-key` 参数 / Notebook 单元格传入。详见 `module_stepfun_vision/README.md`。

**路径与 sudo 密码。** 脚本中的 `/home/jetbot/Notebook/the21thYDS/...` 是比赛时 Jetbot 设备上的真实部署路径，换机器请自行修改。`jetbot_init_and_selfcheck.py` 内含 Yahboom 出厂公开默认 sudo 密码，仅适用于原厂镜像；自定义系统请改用 `JETBOT_SUDO_PASSWORD` 环境变量或 `--prompt-password` 参数。

## 启动

巡检主入口是网页控制台，在 Jetbot 上运行：

```bash
cd /home/jetbot/Notebook/the21thYDS/module_web_dashboard
python3 dashboard_server.py --host 0.0.0.0 --port 8060
```

浏览器打开 `http://<jetbot-ip>:8060`，确认场地安全后点击「启动巡检」。也可不经网页、直接单独运行编排器：

```bash
cd module_agent_orchestrator
python3 inspection_agent_orchestrator.py --help
```

> 编排器会驱动小车运动。首次调试建议先架空履带或清空周围区域；`jetbot_system_check.py` 与 `jetbot_init_and_selfcheck.py` 可在不动车的前提下检查环境（含可选 `--motion-test`）。

## 目录说明

```
module_*/            论文第 4 章的九个工具模块（各含 .py / .ipynb / README.md）
TTS/                 AI 语音模块协议、命令词表与串口示例
new/                 Jetbot 官方基础例程（运动 / RGB 灯 / 蜂鸣器）
notebook/            开发期 notebook 副本（与 module_* 内的 notebook 对应）
yunt/                云台舵机串口控制例程
根目录 *.py/*.ipynb  定位牌生成、二维码标定验证、系统自检等脚本
docs/                原始代码目录说明
代码提交说明.md      提交包自带的运行说明
```

本仓库按「完整保留提交包」原则归档，上述目录（含重复 notebook 与官方例程）均原样保留，便于对照开发过程；实际部署主要用到 `module_*/` 与根目录的主流程脚本。

## 许可证

MIT — 见 [LICENSE](LICENSE)。
