# 机器协议（JSON Lines v1）

MidPnP Studio 通过 UTF-8、换行分隔的 JSON（JSONL）与贴片机控制器通信。TCP 与串口共用同一套消息格式。

- TCP 默认端口：`5025`
- 串口默认：`115200 8N1`
- 每行必须是一个完整 JSON 对象，以 `\n` 结尾
- 单条消息建议小于 64 KB
- 命令超时默认 10 秒

## 1. 消息类型

### 请求（上位机 → 控制器）

```json
{"id": 12, "cmd": "move", "args": {"x": 120.5, "y": 88.0, "z": 10.0}}
```

`id` 单调递增且必须原样返回。

### 成功响应（控制器 → 上位机）

```json
{"id": 12, "ok": true, "result": {"state": "ready", "x": 120.5, "y": 88.0, "z": 10.0}}
```

### 失败响应

```json
{"id": 12, "ok": false, "error": "Z 轴软限位触发"}
```

`error` 应为可直接展示给操作员的中文/英文短句。

### 事件（控制器 → 上位机，可异步）

```json
{"event": "state", "data": {"state": "running"}}
{"event": "position", "data": {"x": 120.5, "y": 88.0, "z": 10.0}}
{"event": "vacuum", "data": {"on": true}}
{"event": "feeder", "data": {"id": "FDR-01", "slot": 1, "remaining": 3119}}
```

事件没有 `id`，上位机在等待响应期间会持续消费事件。

## 2. 坐标与单位

- 单位：毫米（mm），角度：度（°）
- 机器坐标原点：台面左下角，X 向右、Y 向上、Z 向上
- 板内坐标 → 机器坐标：`machine = board_origin + placement`
- 旋转角：板面逆时针为正；控制器负责吸嘴旋转方向映射

## 3. 命令

| 命令 | 参数 | 返回 | 说明 |
| --- | --- | --- | --- |
| `ping` | 无 | `{"ok": true, "name": "...", "version": "..."}` | 连通性检查 |
| `status` | 无 | 状态对象 | 连接后第一条命令 |
| `home` | 无 | 状态对象 | 回原点，完成后 `state=ready` |
| `move` | `x,y,z?,speed?` | 状态对象 | 绝对移动；未给 z 保持当前 Z |
| `jog` | `dx,dy,dz,speed?` | 状态对象 | 相对点动，受软限位 |
| `pick` | `slot` 或 `feeder_id`, `nozzle` | `{"picked": true, ...}` | 打开真空、取料 |
| `place` | `x,y,rotation` | `{"placed": true}` | 关真空、贴装；可先移动到目标点 |
| `feed` | `slot` 或 `feeder_id`, `count?` | `{"remaining": n}` | 料带前进并扣减余料 |
| `vacuum` | `on` | `{"vacuum": bool}` | 手动真空 |
| `nozzle` | `nozzle: "N1"` | `{"nozzle": "N1"}` | 切换吸嘴 |
| `conveyor` | `action: feed/reverse/stop` | `{"conveyor": "..."}` | 传送带 |
| `lights` | `on` | `{"lights": bool}` | 照明 |
| `clear_fault` | 无 | 状态对象 | 复位报警/急停 |
| `estop` | 无 | 状态对象 | 软件急停（非安全回路） |
| `get_feeders` | 无 | `{"feeders": [...]}` | 读取控制器侧料站状态 |

### 状态对象

```json
{
  "state": "ready",
  "x": 120.0,
  "y": 88.0,
  "z": 12.0,
  "vacuum": false,
  "nozzle": "N1",
  "homed": true,
  "conveyor": "stopped",
  "lights": false,
  "placed": 12
}
```

`state` 可取：`offline / idle / ready / homing / running / paused / error / estop`。

## 4. 一次贴装的事务序列

上位机按 JobPlan 逐步发送：

```
move(pick_x, pick_y, z=pick_z)   # 移动到取料点
pick(slot, nozzle)               # 开真空取料
feed(slot, 1)                    # 料带前进一格
move(place_x, place_y, z=10)     # 搬运到贴装点上方
place(place_x, place_y, rotation)
```

若任一步返回 `ok=false`，本次生产进入 `Faulted` 或 `E-Stopped`，上位机停止发送后续步骤。控制器应保证失败时关闭真空并抬升 Z。

## 5. 超时、重连与错误

- 上位机每个请求等待 10 秒；超时视为通信故障并断开连接。
- 控制器主动断开时，上位机进入 `ERROR` 并提示检查日志。
- 事件可以穿插在响应之间，适配器会先消费事件再匹配 `id`。
- 上位机不自动重试运动命令，避免重复动作造成撞机；重连由操作员确认。

## 6. 安全

- `estop` 命令是软件级停止，**不是安全等级急停**。
- 真机必须有独立的硬件急停、STO、安全门/光栅联锁；上位机只能作为辅助。
- 首次联调建议：空载、低速（≤10%）、单步、软限位内验证每个轴与真空 IO。
- `move` 前控制器必须自行校验软限位；不能只依赖上位机。

## 7. 独立模拟器

仓库自带一个符合本协议的 TCP 服务端：

```powershell
python tools\machine_sim_server.py --host 127.0.0.1 --port 5025 --speed 20
```

用 `nc` / PuTTY / 自写脚本发送一行请求即可测试：

```json
{"id":1,"cmd":"status","args":{}}
```

它内部复用 `SimulatorBackend`，会真实地执行取料、贴装、扣减余料，并推送 `position/state/vacuum/feeder` 事件，适合作为控制器开发的对标实现。
