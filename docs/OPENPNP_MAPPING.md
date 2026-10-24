# OpenPnP 移植对照

参考源码：`https://github.com/openpnp/openpnp`（本机检出 `main`，commit `5bd404cf`，
2026-02-27）。分析结论均来自实际代码，未按印象补全。

> 先纠正一个常见误解：OpenPnP 的接口在 `spi/`、基类在 `spi/base/`、实现在
> `machine/reference/`；`GcodeDriver` 在 `machine/reference/driver/`，
> `ReferenceCamera` 在 `machine/reference/camera/`。序列化用 SimpleXML
> （`HyphenStyle`），不是自研 `sp` 包。

## 1. 模块对照

| OpenPnP | 本项目 | 状态 |
| --- | --- | --- |
| `model/Machine` + `ReferenceMachine` | `core/profiles/schema.py` `MachineProfile` | ✅ 结构对齐（JSON） |
| `machine.xml`（SimpleXML） | `midpnp/data/profiles/*.json` | ✅ 等价字段 |
| `AxesLocation` / `Location` / `Length` | `MachineLimits` + 各配置的 mm 字段 | ✅ 统一 mm/deg |
| `Axis` + `toRaw/toTransformed` 变换栈 | `AxisConfig`（行程/速度/inverted） | ⚠️ 无变换栈 |
| `Head` / `Nozzle` / `NozzleTip` | `HeadConfig` / `NozzleConfig` | ✅ 偏置/标签；❌ runout 校准 |
| `Camera` / `ReferenceCamera` | `CameraConfig` + `vision/cameras.py` | ✅ 结构；❌ 畸变/轴偏角 |
| `Driver` / `GcodeDriver` 命令表 | `core/machine/gcode.py` | ✅ 模板变量/应答/超时 |
| `Feeder` 类型（tape/reel/tray） | `Feeder`（数据库）+ 料站布局 | ⚠️ 仅槽位式 |
| `JobProcessor` / `PnpJobProcessor` | `core/machine/service.py` + `planner.py` | ⚠️ 单头顺序执行 |
| `ReferenceFiducialLocator` | `vision/fiducial.py` | ✅ 仿射/校验/不写回 Placement |
| `ReferenceBottomVision` | `vision/bottom.py` | ✅ 中心/角度；⚠️ 未接生产线程 |
| `CvPipeline` + stages | `vision/pipeline.py` + `stages.py` | ⚠️ 13 个 stage（原版 60+） |
| `VisionUtils`（像素↔机器） | `vision/calibration.py` | ✅ Y 取反、角度取反 |
| `gui/importer` 九种导入器 | `core/imports/` | ⚠️ CSV/KiCad/OpenPnP 板文件 |
| `Package` / `Part` / `Footprint` | `core/packages/library.py` | ⚠️ 合并为 Package + 元件引用 |
| 自动封装匹配 | `core/packages/library.py` 匹配器 | ✅ 自建（OpenPnP 无此功能） |

图例：✅ 已实现 / ⚠️ 部分实现 / ❌ 未实现。

## 2. 照搬的设计点

1. **像素 Y 与角度取反**（`VisionUtils.getPixelOffsets/getPixelAngle`）：
   机器系右手、Y 向上；像素系 Y 向下，换算必须翻号。
2. **补偿只落在板卡变换**：基准点对齐产出 `Affine`（板内 → 机器），
   贴装点本身不改写；规划时现算。
3. **2 点相似 / ≥3 点最小二乘**：2 个基准点解不出剪切与各向异性缩放。
4. **合理性校验再采纳**：缩放 >5%、剪切 >5%、原点偏移超限就拒绝，并保留旧状态。
5. **G-code 命令表**：抽象动作 → 模板变量（`{Name:%.4f}` 的思路），
   未提供的变量删除整段；应答按 `ok` 结束。
6. **机型即配置**：轴/头/吸嘴/相机/供料器/驱动/视觉/安全全部进配置，
   业务层不写死行程与吸嘴数量。

## 3. 有意的偏差

| 方面 | OpenPnP | 本项目 | 原因 |
| --- | --- | --- | --- |
| 配置格式 | XML + SimpleXML | JSON | 易手改、易 diff、PyInstaller 打包简单 |
| 图像库 | OpenCV | numpy | 免重型依赖；仿真场景够用，接口可替换 |
| 视觉管线 | 60+ stage、模板匹配、OCR | 13 个 stage | 先覆盖基准点/对中最小闭环 |
| 板卡坐标 | `BoardLocation` 嵌套变换 | 产品自带 `alignment` | 单板、单机场景简化 |
| 供料器 | tape/reel/tray/自动换料 | 槽位式 + 手动补料 | 主链路先跑通 |
| 调度 | 多吸嘴/多头/换嘴/飞行对中 | 单头顺序 | 见下节路线 |

## 4. 尚未移植（按优先级）

1. 底部对中接入生产循环（贴装前拍照 → 实时补偿），需要相机接口进入机器线程；
2. 多吸嘴/多头任务分解与喷嘴交换（`PnpJobProcessor` 的步骤规划）；
3. 模板匹配基准点（`MatchTemplate` + `CreateFootprintTemplateImage`）；
4. 吸嘴 runout / 视觉偏置标定；
5. 供料器类型扩展（编带/托盘/管装）与自动换料；
6. Gerber / ODB++ / IPC-2581 解析，MES / IPC-CFX / OPC UA 接口；
7. 真实运动控制卡适配（固高、雷赛、Galil）——目前是 G-code / JSONL 适配层。

## 5. 验证方式

- `python -m unittest discover -s tests`：91 项，覆盖配置/匹配/导入/仿射/对中/G-code；
- `tools/smoke_production.py`：连接模拟器 → 35 点生产 → 落库 → 余料校验；
- 界面对位页：仿真相机 → 3 基准点 → 0.25° / 0.35 mm 偏移可复原并应用。
