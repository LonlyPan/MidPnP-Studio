"""机器状态展示映射。"""

from __future__ import annotations

from ..core.models import MachineState
from .theme import COLORS

STATE_LABELS: dict[MachineState, str] = {
    MachineState.OFFLINE: "离线",
    MachineState.CONNECTING: "连接中",
    MachineState.IDLE: "待命",
    MachineState.HOMING: "回原点",
    MachineState.READY: "就绪",
    MachineState.RUNNING: "生产中",
    MachineState.PAUSED: "已暂停",
    MachineState.ERROR: "报警",
    MachineState.ESTOP: "急停",
}

STATE_COLORS: dict[MachineState, str] = {
    MachineState.OFFLINE: COLORS["muted"],
    MachineState.CONNECTING: COLORS["blue"],
    MachineState.IDLE: COLORS["blue"],
    MachineState.HOMING: COLORS["warn"],
    MachineState.READY: COLORS["accent"],
    MachineState.RUNNING: COLORS["accent"],
    MachineState.PAUSED: COLORS["warn"],
    MachineState.ERROR: COLORS["danger"],
    MachineState.ESTOP: COLORS["danger"],
}


def state_label(state: MachineState) -> str:
    return STATE_LABELS.get(state, state.value)


def state_color(state: MachineState) -> str:
    return STATE_COLORS.get(state, COLORS["muted"])
