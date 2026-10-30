# 机型配置（Machine Profile）

机型配置解决一件事：**换一台机器只换 JSON，不改代码**。

参考 OpenPnP 的 `machine.xml`：一台机器由「轴 → 头/吸嘴 → 相机 → 供料器 → 驱动 →
视觉参数 → 安全参数」描述。OpenPnP 用 SimpleXML 序列化，本项目用等价的 JSON，
字段语义尽量对齐，便于对照阅读和迁移。

## 1. 文件位置与加载顺序

| 层级 | 路径 | 说明 |
| --- | --- | --- |
| 内置模板 | `midpnp/data/profiles/*.json` | 随程序发布，只读；可直接复制出来改 |
| 用户配置 | `<数据目录>/profiles/*.json` | 界面“另存为/导入”写入，同 ID 时覆盖内置 |

数据目录默认 `%LOCALAPPDATA%\MidPnP Studio\`，可用 `--data-dir` 或
`$env:MIDPNP_DATA_DIR` 覆盖。当前机型记录在 `settings.json` 的
`machine_profile_id` 字段里。

切换方式（三种都行）：

1. **图形化画廊（推荐）**：首次启动会自动弹出「选择你的设备」；之后从
   **系统设置 → 机型配置 → 更换 / 添加设备** 打开同一个画廊。点卡片预览，
   双击或点「使用此机型」确认；画廊里还能导入配置、另存副本、导出、删除。
2. 界面：**系统设置 → 机型配置 → 更换 / 添加设备**，或点左上角设备照片；
3. 手改 `settings.json` 的 `machine_profile_id`，重启程序。

> 首次启动的判断条件是 `settings.json` 里既没有 `machine_profile_id`、
> `machine_selected` 也是 false。选过或点过「稍后再说」后不再弹出。

## 2. 内置模板

| ID | 名称 | 用途 |
| --- | --- | --- |
| `sim-desktop` | MidPnP M1 · 双吸嘴（模拟） | 420×360、2 吸嘴、上下各 25 飞达、双相机；默认模板，演示数据配套 |
| `bench-single` | 桌面单吸嘴机 · 300×300 | 单吸嘴小台面，1 个俯视相机 |
| `gcode-3axis` | G-code 三轴机 · 600×500（模板） | 演示 G-code 命令表 + TCP 链路 |
| `dual-head-demo` | 双头四吸嘴 · 450×400（示例） | 演示多头配置结构 |

> 除 `sim-desktop` 外都是**模板**，尺寸与命令只为展示结构，上机前必须按实际机器修改。

## 3. 结构

```jsonc
{
  "schema": "midpnp.machine-profile/1",
  "id": "sim-desktop",
  "name": "MidPnP M1 · 双吸嘴（模拟）",
  "description": "…",
  "vendor": "MidPnP Studio",
  "image": "machines/m1.png",
  "tags": ["simulator"],
  "axes": { "x": {…}, "y": {…}, "z": {…}, "c": {…} },
  "heads": [ { "id": "H1", "nozzles": [ {…} ] } ],
  "cameras": [ {…} ],
  "feeders": {…},
  "driver": {…},
  "vision": { "fiducial": {…}, "bottom": {…} },
  "safety": {…}
}
```

### 3.1 轴 `axes`

| 字段 | 含义 | 默认 |
| --- | --- | --- |
| `unit` | `mm` 或 `deg`（旋转轴） | X/Y/Z 为 mm，C 为 deg |
| `min` / `max` | 软限位范围 | 0–400 |
| `home` | `min`/`max`/`zero`/`center`/`none` | 直线轴 `min`，C 轴 `zero` |
| `max_speed` | 最大速度 mm/s（或 °/s） | 300 |
| `accel` | 加速度 | 2000 |
| `steps_per_mm` | 步进当量 | 80 |
| `inverted` | 方向取反 | false |
| `soft_limit` | 是否启用软限位 | true |

规划器按 `min_x/min_y` 与 `travel_*` 校验坐标；`c` 轴不参与行程校验。

### 3.2 头与吸嘴 `heads[].nozzles[]`

| 字段 | 含义 |
| --- | --- |
| `id` / `name` | 吸嘴编号与显示名 |
| `tip_diameter_mm` | 吸嘴口径，用于按元件尺寸选嘴 |
| `max_part_height_mm` | 可容纳的元件高度 |
| `offset` | 相对头坐标的偏置 `{x,y,z}` |
| `rotation_axis` | 旋转轴 ID（通常是 `c`） |
| `vision_pipeline` | 该吸嘴的底部对中流水线名 |
| `pick_dwell_ms` / `place_dwell_ms` | 取料/贴装停留时间 |
| `compatible_tags` | 兼容的封装标签，如 `chip`、`ic`、`connector` |

选嘴规则：封装标签 ∩ 吸嘴标签优先，其次考虑元件高度与吸嘴口径；全不命中时
回退到元件库里手工指定的吸嘴。

### 3.3 相机 `cameras[]`

| 字段 | 含义 |
| --- | --- |
| `mount` | `head`（随头）/`fixed`（固定）/`gantry` |
| `resolution` | `[宽, 高]` 像素 |
| `pixels_per_mm` | 像素当量（标定值），必须 > 0 |
| `offset` | 随头相机相对吸嘴的偏置 |
| `location` | 固定相机的机器坐标 |
| `pipeline` | 默认流水线名（`fiducial-default` / `bottom-default` …） |
| `lighting` | `ring` / `backlight` / `none`（仅记录，供驱动实现） |
| `exposure_ms` | 曝光（仅记录/仿真用） |

> 真实相机还需要镜头畸变、轴偏角等标定参数；当前版本只支持像素当量 + 平移偏置。

### 3.4 供料器 `feeders`

```jsonc
{ "type": "slot", "slot_count": 50, "first_slot": 1,
  "slot_pitch_mm": 10.0, "tape_pitch_mm": 4.0,
  "origin": {"x": 18.0, "y": 330.0}, "direction": "x",
  "top_count": 25, "bottom_count": 25 }
```

`origin` 是 1 号槽的取料点，`direction` 为 `x` 或 `y`。
`top_count` / `bottom_count` 描述上下两排飞达数量（M1 为各 25 个）：上排槽位
`1..25`、下排 `26..50`；首页整机线稿按这个分区绘制，并按数据库中已装料，
显示为绿色/黄色/虚线三种状态。为 0 时表示不分区，沿用 `slot_count`。

### 3.5 设备图片 `image`

```jsonc
"image": "machines/m1.png"
```

相对 `assets/` 目录，会显示在侧边栏设备卡、设备画廊卡片和连接弹窗里；
缺省时退回矢量示意图。图片建议用去白底的 PNG（透明背景）。

### 3.6 驱动 `driver`

| `type` | 链路 | 说明 |
| --- | --- | --- |
| `simulator` | 内置 | 虚拟贴片机，无需硬件 |
| `jsonl-tcp` / `jsonl-serial` | TCP / 串口 | 本项目的 JSON Lines 协议 |
| `gcode-tcp` / `gcode-serial` | TCP / 串口 | 命令表渲染成 G-code |

`commands` 是「抽象动作 → 命令模板」映射，支持的变量：

| 变量 | 含义 |
| --- | --- |
| `{x}` `{y}` `{z}` `{dx}` `{dy}` `{dz}` | 坐标，保留 3 位小数 |
| `{speed}` | 进给速度，已由 mm/s 换算为 mm/min |
| `{rotation}` | 贴装角度 |
| `{slot}` `{count}` | 料站号 / 数量 |
| `{nozzle}` `{nozzle_index}` | 吸嘴 ID / 序号 |
| `{delay}` | 取放停留秒数（来自吸嘴配置） |
| `{vacuum_pin}` `{state}` | 真空输出脚 / 开关状态 |
| `{action}` | 传送带等动作名 |

未提供的变量渲染为空串，便于“整段删除”。应答默认以 `ok_responses` 里的 token
结束；同一行里出现 `error` 即抛错。`status` 命令会尝试解析 `X: Y: Z:`。

### 3.7 视觉 `vision`

```jsonc
"fiducial": { "search_radius_mm": 12, "threshold": 0.45, "min_area_mm2": 0.3,
              "max_area_mm2": 80, "shape": "circle", "min_score": 0.55, "required": 1 },
"bottom":   { "max_offset_mm": 2.0, "max_angle_deg": 20, "angle_step_deg": 1.0,
              "min_score": 0.55, "correction": "both" }
```

### 3.8 安全 `safety`

`safe_z_mm`、`max_speed_mm_s`、`soft_limits`、`estop`、`vacuum_settle_ms`。
`estop: "software"` 只表示软件级停止，**不能替代硬件急停回路**。

## 4. 校验

保存/应用前会校验：轴上下限、回零方式、速度/步进、头与吸嘴 ID 唯一、相机 ID 唯一、
像素当量 > 0、驱动类型、端口范围、料站数量/间距、安全高度是否在 Z 行程内、
视觉阈值/面积范围等。错误会阻止保存，提示只记录不阻止。

## 5. 从 OpenPnP 迁移

| OpenPnP | 本项目 |
| --- | --- |
| `<machine class="ReferenceMachine">` | `MachineProfile` |
| `axes/axis` | `axes[]` |
| `heads/head/nozzles/nozzle` | `heads[].nozzles[]` |
| `cameras/camera` | `cameras[]` |
| `feeders/feeder` | 供料器记录（数据库）+ `feeders` 料站布局 |
| `driver class="GcodeDriver"` | `driver.type = gcode-*` + `commands` |
| `machine.xml` 的 `length-unit` | 统一 mm / deg，不再有单位换算层 |

映射时注意：OpenPnP 的轴有 `Mapped`/`LinearTransform` 变换栈与虚拟轴，本项目只保留
线性行程与 `inverted` 标记；OpenPnP 的 nozzle tip 校准（runout、视觉偏置）暂未实现。
