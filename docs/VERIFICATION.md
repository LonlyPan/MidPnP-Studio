# 验证记录

## 0. v0.3（2026-10-30）

环境：Windows 10 22H2 (19045) · Python 3.13.13 · PySide6 6.12.0 · numpy 2.5.4

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 语法编译 | `python -m compileall -q midpnp tests tools main.py` | 通过（0 错误） |
| 单元测试 | `python -m unittest discover -s tests` | **107 项全部通过** |
| 首页 | `tests/test_home.py`（7 项） | 上下料分区、飞达料号、双相机切换、线稿绘制、未连接横幅 |
| 连接向导 | `tests/test_connect_dialog.py`（2 项） | 四步全部完成并自动关闭；取消可中止 |
| 界面离屏渲染 | `python tools\make_screenshots.py` | 10 个页面 + 连接弹窗 + 设备画廊 |
| 连接实机流程 | 无头脚本 | 相机 2 台 → 主机已连接 → 已回零 → 校准完成，约 2.7 s |
| 设备照片 | `assets/machines/m1.png` | 去白底 PNG，侧边栏/画廊/连接弹窗共用 |

本版新增：首页（相机 + Jog + 整机线稿）、四步连接弹窗、侧边栏设备照片与点击切换、
设备画廊/设置页照片、M1 双吸嘴机型（上下各 25 飞达）。
本期**未**重新执行 PyInstaller 打包；打包脚本已加入 `--add-data assets`，下次
`build.ps1` 时验证。

---

## 0.1 v0.2（2026-10-24）

环境：Windows 10 22H2 (19045) · Python 3.13.13 · PySide6 6.12.0 · numpy 2.5.4 · pyserial 3.5

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 语法编译 | `python -m compileall -q midpnp tests tools main.py` | 通过（0 错误） |
| 单元测试 | `python -m unittest discover -s tests` | **98 项全部通过** |
| 端到端生产 | `python tools\smoke_production.py` | `Completed 35/35 · E2E OK` |
| 界面离屏渲染 | `python tools\make_screenshots.py` | 10 个页面 + 生产中状态 + 设备画廊全部生成 |
| 设备画廊 | `tests/test_machine_gallery.py`（7 项） | 卡片数量/预选/切换/筛选/确认/删除保护/首次启动标题 |
| 机型切换 | 无头脚本切到 `bench-single` | 行程 300 mm 生效，旧料站坐标被正确判为超行程 |
| 视觉对位 | 无头脚本 + 截图 | 3 点仿射复原 0.25° / 0.35 mm（RMS 0.000 mm） |
| 底部对中 | `tests/test_vision.py` | 0.12 mm / 1.2° 可复原（±0.03 mm / ±0.35°） |

新增测试覆盖：机型配置读写/校验/投影、设备画廊交互、封装归一化与匹配打分、CSV/KiCad/OpenPnP 板导入、
单位与镜像变换、仿射求解与合理性校验、仿真相机基准点对齐、底部对中、G-code 命令模板渲染。

本期**未**重新执行 PyInstaller 打包（需要单独安装打包依赖并生成 50 MB 产物）；
打包脚本已加入 `--add-data midpnp\data`，下次 `build.ps1` 时会一并验证。

---

日期：2026-10-23  
环境：Windows 10 22H2 (19045) · Python 3.13.14 · PySide6 6.11.2 · pyserial 3.5

## 1. 静态检查

```powershell
python -m compileall -q midpnp
python -m pyflakes midpnp tests tools main.py
```

结果：通过，0 条告警。

## 2. 单元测试

```powershell
python -m unittest discover -s tests -v
```

结果：**32 个用例全部通过**，覆盖：

- 规划与可制造性检查（重复位号、缺元件、空料、超行程、路径排序）
- JSONL 帧解析、粘包/半包、错误响应、事件分发
- 演示数据、SQLite CRUD、重复槽位、产品复制、日志、今日汇总
- CSV 中英文表头、mil 换算、导出后回读
- 模拟器连接、回零、点动、取放、急停复位、软限位

## 3. 端到端生产

```powershell
python tools\smoke_production.py
```

结果：

```
run status=Completed placed=35/35 duration=4.5s state=ready
feeder stock decremented correctly
E2E OK
```

验证链路：

1. 启动应用并自动连接内置模拟器；
2. 打开演示产品 MX-LED8（35 点）；
3. 通过 UI 启动生产；
4. 依次完成取料、贴装、供料器扣料；
5. 生产记录写入 SQLite；
6. 主机侧供料器余料按实际使用量扣减；
7. 结束后状态回到 `ready`。

## 4. TCP 适配器联调

启动：

```powershell
python tools\machine_sim_server.py --host 127.0.0.1 --port 5025 --speed 20
```

客户端使用 `TcpBackend` 执行 `connect → status → jog(12, 8) → status → disconnect`，返回状态正确，事件与响应匹配正常。

## 5. UI 验证

- 9 个页面均完成离屏渲染截图，见 `docs/screenshots/`。
- 1280×820 最小窗口下，生产页、编程页、总览页可正常使用；总览页内容可滚动。
- 生产运行截图与 35 点完成截图均已生成。
- 对话框（元件/贴片点/供料器/问题清单/删除确认）构造与返回值验证通过。
- 手动点动、视觉对位、页面跳转、Toast、状态栏坐标同步均验证。

## 6. Windows 打包

```powershell
.\build.ps1
```

结果：

- `dist\MidPnPStudio\MidPnPStudio.exe` 生成成功；
- 打包后 `--smoke-test` 退出码 0，自动创建数据目录与数据库；
- `release\MidPnPStudio-v0.1.0-win64.zip` 生成成功（约 50 MB）。

## 7. 未验证项（需要真实硬件）

- 真实运动控制卡 / PLC 的指令映射与 IO 时序；
- 工业相机 SDK、镜头标定与真实 Mark 识别精度；
- 吸嘴交换、多头并行、飞行对中；
- 硬件急停、安全门、光栅的安全等级验证；
- 长时间连续运行、粉尘/振动/温漂下的稳定性。

这些项目必须在真实设备上按厂商协议、安全规范和现场工艺单独验证，不能以本仓库的仿真结果代替。
