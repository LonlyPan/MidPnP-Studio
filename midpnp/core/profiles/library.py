"""机型配置库：内置模板（只读）+ 用户配置（数据目录 profiles/*.json）。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .schema import MachineProfile, ProfileIssue, validate_profile


def builtin_profiles_dir() -> Path:
    """仓库/安装包内置的示例机型目录。"""
    return Path(__file__).resolve().parents[2] / "data" / "profiles"


def user_profiles_dir(data_root: str | Path) -> Path:
    return Path(data_root) / "profiles"


class ProfileError(ValueError):
    """机型配置读写失败。"""


class ProfileLibrary:
    """合并内置模板与用户配置；同 ID 时用户配置优先。"""

    def __init__(self, data_root: str | Path, builtin_dir: str | Path | None = None) -> None:
        self.data_root = Path(data_root)
        self.builtin_dir = Path(builtin_dir) if builtin_dir else builtin_profiles_dir()
        self._profiles: dict[str, MachineProfile] = {}
        self.refresh()

    # ---------------- 读取 ----------------

    def refresh(self) -> None:
        self._profiles = {}
        for profile in self._load_dir(self.builtin_dir, builtin=True):
            self._profiles[profile.id] = profile
        for profile in self._load_dir(user_profiles_dir(self.data_root), builtin=False):
            self._profiles[profile.id] = profile

    def _load_dir(self, directory: Path, builtin: bool) -> list[MachineProfile]:
        if not directory.exists():
            return []
        result: list[MachineProfile] = []
        for path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            try:
                profile = MachineProfile.from_dict(data)
            except (TypeError, ValueError):
                continue
            if not profile.id:
                profile.id = path.stem
            if not profile.name:
                profile.name = path.stem
            profile.builtin = builtin
            profile.source_path = str(path)
            result.append(profile)
        return result

    def list(self) -> list[MachineProfile]:
        return sorted(
            self._profiles.values(),
            key=lambda profile: (profile.builtin, profile.name),
        )

    def ids(self) -> list[str]:
        return [profile.id for profile in self.list()]

    def get(self, profile_id: str) -> MachineProfile | None:
        return self._profiles.get(profile_id)

    def default(self) -> MachineProfile | None:
        profiles = self.list()
        if not profiles:
            return None
        preferred = self._profiles.get("sim-desktop")
        return preferred or profiles[0]

    # ---------------- 写入 ----------------

    def save(self, profile: MachineProfile, overwrite_builtin: bool = False) -> Path:
        issues = [issue for issue in validate_profile(profile) if issue.is_error]
        if issues:
            raise ProfileError("；".join(f"{issue.field}: {issue.message}" for issue in issues))
        existing = self._profiles.get(profile.id)
        if existing is not None and existing.builtin and not overwrite_builtin:
            raise ProfileError(
                f"机型 {profile.id} 是内置模板，请先“另存为”新 ID 再编辑，避免覆盖示例配置"
            )
        directory = user_profiles_dir(self.data_root)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{_safe_name(profile.id)}.json"
        _write_json_atomic(target, profile.to_dict())
        profile.builtin = False
        profile.source_path = str(target)
        self._profiles[profile.id] = profile
        return target

    def delete(self, profile_id: str) -> bool:
        profile = self._profiles.get(profile_id)
        if profile is None:
            return False
        if profile.builtin:
            raise ProfileError("内置模板不能删除")
        path = user_profiles_dir(self.data_root) / f"{_safe_name(profile_id)}.json"
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            raise ProfileError(f"删除配置文件失败：{exc}") from exc
        self._profiles.pop(profile_id, None)
        return True

    def duplicate(self, source_id: str, new_id: str, new_name: str = "") -> MachineProfile:
        source = self.get(source_id)
        if source is None:
            raise ProfileError(f"未找到机型 {source_id}")
        if source_id == new_id and source.builtin:
            raise ProfileError("新 ID 必须与内置模板不同")
        data = source.to_dict()
        data["id"] = new_id
        data["name"] = new_name or f"{source.name} 副本"
        clone = MachineProfile.from_dict(data)
        clone.builtin = False
        self.save(clone)
        return clone

    def export(self, profile: MachineProfile, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(target, profile.to_dict())
        return target

    def import_file(self, path: str | Path) -> MachineProfile:
        source = Path(path)
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProfileError(f"读取配置文件失败：{exc}") from exc
        if not isinstance(data, dict):
            raise ProfileError("配置文件顶层必须是 JSON 对象")
        profile = MachineProfile.from_dict(data)
        if not profile.id:
            profile.id = source.stem
        if not profile.name:
            profile.name = source.stem
        # 导入即视为用户配置：允许用同名 ID 覆盖内置模板（写入用户目录，不改仓库文件）
        self.save(profile, overwrite_builtin=True)
        return profile


def _safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in value.strip())
    return cleaned or "machine"


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def load_profile(
    data_root: str | Path,
    profile_id: str = "",
    fallback: Any | None = None,
) -> MachineProfile | None:
    """加载指定机型；为空则取默认；全部失败时用 fallback 设置合成。"""
    library = ProfileLibrary(data_root)
    if profile_id:
        profile = library.get(profile_id)
        if profile is not None:
            return profile
    default = library.default()
    if default is not None:
        return default
    if fallback is not None:
        return MachineProfile.from_settings(fallback)
    return None


def profile_issues_text(issues: list[ProfileIssue]) -> str:
    if not issues:
        return "配置校验通过"
    return "\n".join(
        f"[{'错误' if issue.is_error else '警告'}] {issue.field}：{issue.message}" for issue in issues
    )
