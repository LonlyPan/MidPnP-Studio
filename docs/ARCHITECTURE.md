# 架构设计

## 1. 目标与边界

MidPnP Studio 的目标是提供一个可运行的贴片机上位机骨架，覆盖「产品数据 → 工艺检查 → 路径规划 → 机器执行 → 生产记录」主链路，同时把机器、视觉、数据库隔离在可替换的边界之后。

v0.1 不是完整的量产机型控制软件，边界如下：

- 单吸嘴顺序贴装，不包含多头并行、吸嘴自动交换、飞行对中。
- 视觉是离线仿真，未绑定具体相机 SDK。
- 真实运动控制卡、安全 PLC 未接入；通过 JSONL 适配层预留。
- 只实现单机生产，不含 MES / 排产 / 权限中心。

## 2. 分层

```
┌──────────────────────────────────────────────────────────┐
│ UI (PySide6)                                             │
│  MainWindow · Dashboard · Production · Programming · ...  │
│  BoardView / MetricCard / RingProgress / Toast             │
└───────────────▲───────────────────────────────┬──────────┘
                │ Qt Signals                    │ user actions
┌───────────────┴───────────────────────────────▼──────────┐
│ AppContext / AppSignals                                   │
│  跨页面事件（产品、供料器、日志、导航、Toast）              │
└───────────────▲───────────────────────────────┬──────────┘
                │                                │
┌───────────────┴──────────────┐  ┌──────────────▼─────────┐
│ Domain / Services            │  │ Storage                │
│  models / planner            │  │  SQLite + JSON payload  │
│  MachineService (QThread)    │  │  WAL, RLock             │
└───────────────▲──────────────┘  └────────────────────────┘
                │ synchronous commands
┌───────────────┴──────────────────────────────────────────┐
│ Machine adapters                                         │
│  SimulatorBackend · TcpBackend · SerialBackend           │
└──────────────────────────────────────────────────────────┘
```

### 2.1 领域层（`midpnp/core`）

纯 Python，不依赖 Qt，可直接单元测试：

- `models.py`：`Product / Placement / Component / Feeder / JobPlan / RunRecord` 等 dataclass，带 `to_dict/from_dict`。
- `planner.py`：生产前检查与路径规划，返回 `JobPlan` 和 `ValidationIssue` 列表。
- `importers.py`：EDA 坐标 CSV 解析 / 导出。
- `protocol.py`：JSONL 增量帧解析、请求跟踪、错误类型。
- `storage.py`：SQLite 持久化，线程安全。

### 2.2 机器层（`midpnp/core/machine`）

`MachineBackend` 是同步命令接口：

```python
connect() -> dict
disconnect() -> None
command(name: str, **args) -> dict
request_stop() -> None
```

`MachineService(QObject)` 独占一个后台线程，所有机器命令串行进入队列。生产任务在同一个工作线程内顺序执行，避免与手动命令竞争。UI 只通过 Qt Signal 接收状态、坐标、真空、生产进度。

```
UI thread                  machine-io thread
   │ connect_machine()          │
   ├──── queue.put("connect") ─►│ backend.connect()
   │                            │ emit state/position  ──► queued to UI
   │ start_job(plan)            │
   ├──── queue.put("job") ─────►│ for step:
   │                            │   move → pick → feed → move → place
   │◄── run_progress ───────────┤
   │◄── run_finished ───────────┤
```

状态机：

```
OFFLINE → CONNECTING → READY/IDLE
READY → HOMING → READY
READY → RUNNING ⇄ PAUSED
RUNNING → READY | ERROR | ESTOP
ERROR/ESTOP → (clear_fault) → READY
```

### 2.3 UI 层

- 主窗口负责侧边导航、顶栏、状态栏、报警横幅、Toast。
- 每个页面只依赖 `AppContext`，不直接访问其他页面。
- 跨页面刷新走 `AppSignals`：`products_changed / components_changed / feeders_changed / log_added`。
- 板卡画布 `BoardView` 支持板卡坐标与机器坐标两种视图、缩放、平移、贴装点选择、贴装状态着色、贴装头十字线。
- 深色主题全部由 QSS 定义，图标由 QPainter 矢量生成，无外部图片依赖。

## 3. 数据模型

- **Product**：板框尺寸、板厚、板原点（机器台面坐标）、Mark 点、贴装点。
- **Placement**：位号、元件 ID、板内坐标（mm，左下角为原点）、旋转角、正反面、DNP、锁定。
- **Component**：封装、长宽高、吸嘴、视觉策略、速度、显示颜色。
- **Feeder**：槽位（1–99）、元件、容量、余料、料带间距、取料坐标、低料阈值、启用状态。
- **JobStep**：规划后的单步，含取料点、贴装点、吸嘴、旋转角、供料器槽位。
- **RunRecord**：批次、产品、起止时间、总数、成功、失败、跳过、状态、时长。

机器坐标 = 板原点 + 板内坐标。

## 4. 路径规划

1. 检查：空产品、重复位号、缺失元件、无供料器、空料、超行程、重复槽位、板外坐标。
2. 为每个贴装点选择供料器：优先显式 `feeder_id`，否则选同元件、启用、余料最多的料站。
3. 最近邻排序，代价为「当前点 → 取料点 + 取料点 → 贴装点」，减少空行程。
4. 估算节拍：距离 / 有效速度 + 固定取放开销，用于进度环与 ETA。
5. 任何 error 级问题都会阻止开始生产；warning 允许继续但会提示。

规划是确定性的，不依赖随机数，便于测试和复现。

## 5. 持久化

单文件 SQLite，WAL 模式，进程内 `RLock` 串行写。复杂对象以 JSON payload 存储，索引列单独冗余，便于查询与迁移。

```
components(id, name, package, payload)
feeders(id, slot UNIQUE, component_id, payload)
products(id, name, revision, updated_at, payload)
runs(id, product_id, ..., started_at, finished_at, status, payload)
logs(id, timestamp, level, source, message)
meta(key, value)
```

首次启动写入演示数据；`settings.json` 独立保存应用配置，避免把环境相关参数混入业务数据。

## 6. 线程与信号

- `MachineService` 用 `queue.Queue` 接收命令，独立 daemon 线程处理。
- 工作线程不直接操作任何 QWidget，也不写数据库；只发 Signal。
- 生产结束信号回到 UI 线程后，由 `AppContext.record_run()` 落库并扣减供料器余料。
- 暂停/停止/急停使用 `threading.Event`，从 UI 线程置位；适配器在运动循环的安全点检查中止。
- 急停额外入队 `estop` 命令，保证任务结束后机器进入急停状态。

## 7. 适配真实硬件

实现新的 `MachineBackend` 并在 `MachineService._do_connect()` 注册即可。推荐步骤：

1. 明确控制器协议（寄存器 / G-code / 厂商 SDK / OPC UA）。
2. 把底层命令映射到统一的 `home / move / pick / place / feed / estop` 语义。
3. 实现单位换算、超时、重试、断线重连和错误码翻译。
4. 用 `tools/machine_sim_server.py` 先验证协议，再空载低速上机。
5. 硬件安全回路必须独立于本软件。

## 8. 安全设计

- 软限位在适配器和规划层双重校验。
- 手动命令在生产中被锁定。
- 生产前检查阻止缺料、超行程、缺元件。
- 急停有界面红色按钮、报警横幅、状态机与日志。
- 但软件急停**不满足功能安全要求**，不能替代硬件急停、安全门、光栅和 STO。

## 9. 测试策略

- 领域层单元测试：规划、协议、导入、存储、模拟器（32 个用例）。
- 端到端冒烟：启动主窗口 → 自动连接模拟器 → 运行 35 点 → 校验数据库记录与供料器扣减。
- UI 截图离屏渲染：9 个页面 + 生产中状态，用于视觉回归。
- 打包后通过 `--smoke-test` 启动自检。

## 10. 可扩展点

- `VisionPage`：替换 `VisionView` 数据源，接入相机 SDK、标定参数与真实 Mark 识别。
- `MachineService`：支持多吸嘴任务分解、并行头调度、吸嘴交换。
- `planner.py`：替换为 OR-Tools / 遗传算法做多目标优化（换料、吸嘴、路径）。
- `storage.py`：迁移到 PostgreSQL 或通过 repository 接口切换到 MES 数据库。
- `AppContext`：增加用户、角色、电子签名与审计事件。
