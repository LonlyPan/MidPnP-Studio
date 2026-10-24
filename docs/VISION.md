# 机器视觉

视觉模块是纯 numpy 实现（不依赖 OpenCV），接口与 OpenPnP 对齐，可直接在
内置仿真相机上跑通「基准点识别 → 板卡补偿 → 底部对中」全链路。

## 1. 坐标约定（与 OpenPnP 一致，最容易出错的地方）

- 机器坐标系：右手系，X 向右、Y 向上，角度逆时针为正；
- 图像/像素坐标系：Y 向下，因此
  - 像素 Y → 机器 Y 要**取反**：`dy_mm = -(py - h/2) / px_per_mm`
  - 角度要**取反**：`machine_angle = -pixel_angle`
- 板内坐标与机器坐标之间由 `BoardAlignment`（仿射）现算，**不修改贴装点**。

对应 OpenPnP 的 `VisionUtils.getPixelOffsets` / `getPixelAngle`。

## 2. 模块

```
midpnp/core/vision/
├─ geometry.py     # Point2 / Affine / 仿射求解 / 合理性校验 / BoardAlignment
├─ calibration.py  # 像素 ↔ 毫米、角度取反
├─ pipeline.py     # Stage 链、结果模型、JSON 序列化、默认流水线
├─ stages.py       # 具体 stage（阈值/形态学/连通域/最小外接矩形…）
├─ cameras.py      # CameraSource 协议 + SimulatedCamera 渲染
├─ fiducial.py     # 基准点定位、多基准点仿射
└─ bottom.py       # 元件底部对中
```

### 2.1 流水线

一条流水线是若干 `{name, params}` 的有序 stage；执行结果写入 `results` 通道。
与 OpenPnP 的差异：OpenPnP 用 XML 序列化，这里用 JSON；stage 返回 `None` 表示不改图像。

已实现的 stage（命名与 OpenPnP 对齐）：

| 类 | 参数 | 作用 |
| --- | --- | --- |
| `ConvertColor` | `mode` | 转灰度 |
| `BlurGaussian` | `kernel` | 高斯模糊（可分离卷积） |
| `Threshold` | `threshold` / `auto` / `invert` | 全局阈值（`auto` 为 Otsu） |
| `MorphClose` / `MorphOpen` | `kernel` | 闭/开运算 |
| `MaskCircle` | `diameter_mm` | 圆形 ROI |
| `FindContours` | `min_area_px` | 8 连通域 |
| `FilterContours` | `min_area_mm2` / `max_area_mm2` | 面积过滤 |
| `MinEnclosingCircle` | `source` | 最小外接圆 + 圆度评分 |
| `DetectCircularSymmetry` | `min/max_diameter_mm`、`min_score`、`threshold` | 简化版基准点检测器（阈值 + 圆度） |
| `MinAreaRect` | `source` | 最小外接旋转矩形（PCA + 投影） |
| `SelectSingle` | `criterion`（center/largest/score/index） | 从候选里选一个 |
| `SetResult` | `source` | 写入 results |
| `DrawResult` | `show_contours` | 叠加结果（界面显示用） |

内置流水线：`fiducial-default`、`fiducial-simple`、`bottom-default`、`bottom-ic`。

> OpenPnP 原版还有 50+ 个 stage（模板匹配、Hough、OCR、仿射 warp 等），
> 当前只移植了基准点/对中最少集合；接口是开放的，按同样模式新增即可。

### 2.2 基准点对位

```
对每个基准点：
    相机移动到标称位置（仿真：以标称点为中心渲染一帧）
    以标称像素位置为中心裁搜索窗口
    跑流水线 → 取离标称最近的特征 → 像素偏移换算成机器坐标
    （可选）多 pass 收敛：若偏差 > 阈值，用新位置再拍一次
多基准点：
    expected = 板内坐标；measured = 机器坐标
    ≥3 点 → 最小二乘仿射（可解缩放/剪切）
    2 点  → 相似变换（旋转 + 单一缩放 + 平移）
校验：缩放偏离 1 > 5%、剪切 > 5%、原点偏移 > 5 mm → 拒绝本次补偿
结果：BoardAlignment 存到产品 alignment，规划器直接用它换算贴装坐标
```

对应 OpenPnP `ReferenceFiducialLocator` 的 `calculateTransformation`：
同样是「不写回 Placement，只改板卡变换」。

### 2.3 底部对中

```
底部相机拍照 → 流水线找元件矩形 → 中心像素偏移 → 机器坐标偏移
角度：pixel_angle 取反 → 减去期望角 → 折叠到 (-90°, 90°]（矩形 180° 对称）
判定：|dx|、|dy| ≤ max_offset_mm；|θ| ≤ max_angle_deg；置信度 ≥ min_score
输出：PartAlignment（dx/dy/theta + passed + 尺寸），可叠加到贴装目标
```

对应 OpenPnP `ReferenceBottomVision`；差异是 OpenPnP 用变步长角度迭代，
这里用矩形主方向一次求解，适合矩形/片式元件。

## 3. 仿真相机

`SimulatedCamera` 按机型配置的分辨率与 `pixels_per_mm` 渲染：

- 板面：绿色基板 + 焊盘 + 元件本体 + 基准点（金环 + 暗心）+ 暗角 + 噪声；
- 底部：背光 + 吸嘴 + 元件本体 + 端头高亮；
- 随机数固定种子，同样输入得到同样图像，便于回归测试。

接入真实相机：实现 `capture(...) -> Frame`（灰度 0–1 或 0–255 + `CameraCalibration`），
把页面里的 `SimulatedCamera` 替换掉即可；算法层不需要改动。

## 4. 边界

- 未实现镜头畸变、远心镜头、轴偏角标定；只有像素当量 + 平移偏置。
- 未实现 OpenPnP 的模板匹配基准点（`MatchTemplate` + footprint 模板）。
- 未实现多 pass 收敛（当前每点一次拍摄）；对高精度场景建议加 2–3 次迭代。
- 底部对中尚未接入生产线程（界面可测、可导出补偿量；生产仍按板卡补偿执行）。
- 视觉结果依赖光照/对比度：仿真相机对比度理想，真实板卡需要按工艺调阈值。

## 5. 测试

`tests/test_vision.py` 覆盖：仿射求解（3 点/2 点/退化）、合理性校验、
仿真基准点对齐（0.6° / 0.4 mm 偏移可复原，误差 < 0.05 mm）、底部对中
（0.12 mm / 1.2° 可复原）、流水线序列化。
