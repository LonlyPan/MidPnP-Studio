"""贴装路径规划与可制造性检查。"""

from __future__ import annotations

import math
from dataclasses import replace

from .models import (
    Component,
    Feeder,
    JobPlan,
    JobStep,
    MachineLimits,
    Placement,
    Point,
    Product,
    ValidationIssue,
)


def machine_point(product: Product, placement: Placement, alignment: object | None = None) -> Point:
    """将板内坐标转换为机器台面坐标。

    有视觉补偿（`BoardAlignment`）时以补偿矩阵为准——它把板内坐标直接
    映射到机器坐标，替代「板原点 + 板内坐标」的静态换算。
    """
    if alignment is not None and hasattr(alignment, "machine_point"):
        point = alignment.machine_point(placement.x_mm, placement.y_mm)
        return Point(point.x, point.y, 0.0)
    return Point(
        product.board_origin_x_mm + placement.x_mm,
        product.board_origin_y_mm + placement.y_mm,
        0.0,
    )


def nozzle_for_component(
    component: Component,
    profile: object | None = None,
    packages: dict[str, object] | None = None,
) -> str:
    """按机型配置与封装标签选吸嘴；无配置时回退到元件自带吸嘴。"""
    if profile is None or not hasattr(profile, "heads"):
        return component.nozzle
    package = (packages or {}).get(getattr(component, "package_id", ""))
    tags: set[str] = set()
    if package is not None:
        tags.update(str(item) for item in getattr(package, "tags", []))
        tags.add(str(getattr(package, "category", "")))
    else:
        tags.add("chip")
    candidates = []
    for head in getattr(profile, "heads", []):
        for nozzle in getattr(head, "nozzles", []):
            compatibility = {str(item) for item in getattr(nozzle, "compatible_tags", [])}
            overlap = len(tags & compatibility)
            max_height = float(getattr(nozzle, "max_part_height_mm", 6.0))
            fits = component.height_mm <= max_height
            tip = float(getattr(nozzle, "tip_diameter_mm", 0.4))
            # 优先标签命中，其次挑能容纳元件且吸嘴较小的
            candidates.append((overlap, 1 if fits else 0, -tip, nozzle.id))
    if not candidates:
        return component.nozzle
    candidates.sort(reverse=True)
    best = candidates[0]
    if best[0] == 0 and component.nozzle:
        # 没有标签命中时尊重元件库里的手工指定
        return component.nozzle
    return str(best[3])


def validate_job(
    product: Product,
    components: list[Component],
    feeders: list[Feeder],
    limits: MachineLimits,
    alignment: object | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    component_map = {c.id: c for c in components}
    feeder_by_id = {f.id: f for f in feeders}

    if not product.placements:
        issues.append(ValidationIssue("error", "EMPTY_PRODUCT", "产品不包含任何贴装点"))
    if product.board_width_mm <= 0 or product.board_height_mm <= 0:
        issues.append(ValidationIssue("error", "BAD_BOARD", "板卡尺寸必须大于 0"))

    seen: set[str] = set()
    for placement in product.placements:
        ref = placement.refdes.strip()
        if not ref:
            issues.append(ValidationIssue("error", "EMPTY_REF", "存在没有位号的贴装点"))
            continue
        if ref in seen:
            issues.append(ValidationIssue("error", "DUP_REF", f"位号 {ref} 重复", ref))
        seen.add(ref)
        if placement.component_id not in component_map:
            issues.append(
                ValidationIssue(
                    "error",
                    "MISSING_COMPONENT",
                    f"{ref} 引用的元件 {placement.component_id} 不存在",
                    ref,
                )
            )
            continue
        if placement.skip:
            continue

        px, py = product.board_origin_x_mm + placement.x_mm, product.board_origin_y_mm + placement.y_mm
        if alignment is not None and hasattr(alignment, "machine_point"):
            point = alignment.machine_point(placement.x_mm, placement.y_mm)
            px, py = point.x, point.y
        if not limits.contains(px, py):
            issues.append(
                ValidationIssue(
                    "error",
                    "OUT_OF_TRAVEL",
                    f"{ref} 坐标 ({px:.1f}, {py:.1f}) 超出行程 "
                    f"[{limits.min_x_mm:g}–{limits.travel_x_mm:g}]×[{limits.min_y_mm:g}–{limits.travel_y_mm:g}] mm",
                    ref,
                )
            )
        if (
            placement.x_mm < 0
            or placement.y_mm < 0
            or placement.x_mm > product.board_width_mm
            or placement.y_mm > product.board_height_mm
        ):
            issues.append(
                ValidationIssue(
                    "warning",
                    "OUT_OF_BOARD",
                    f"{ref} 位于板框之外 ({placement.x_mm:.1f}, {placement.y_mm:.1f})",
                    ref,
                )
            )

        if placement.feeder_id and placement.feeder_id not in feeder_by_id:
            issues.append(
                ValidationIssue(
                    "error",
                    "BAD_FEEDER_REF",
                    f"{ref} 指定的供料器 {placement.feeder_id} 不存在",
                    ref,
                )
            )
        feeder = _select_feeder(placement, feeders)
        if feeder is None:
            issues.append(
                ValidationIssue(
                    "error",
                    "NO_FEEDER",
                    f"{ref} 使用的 {component_map[placement.component_id].name} 没有可用供料器",
                    ref,
                )
            )
        elif feeder.is_empty:
            issues.append(
                ValidationIssue(
                    "error",
                    "FEEDER_EMPTY",
                    f"供料器 {feeder.slot:02d}（{feeder.label or feeder.id}）余料为 0",
                    ref,
                )
            )
        elif feeder.is_low:
            issues.append(
                ValidationIssue(
                    "warning",
                    "FEEDER_LOW",
                    f"供料器 {feeder.slot:02d} 余料仅 {feeder.remaining_pct}%",
                    ref,
                )
            )
        if feeder is not None:
            if feeder.pick_x_mm < 0 or feeder.pick_x_mm > limits.travel_x_mm or feeder.pick_y_mm < 0 or feeder.pick_y_mm > limits.travel_y_mm:
                issues.append(
                    ValidationIssue(
                        "error",
                        "PICK_OUT_OF_TRAVEL",
                        f"供料器 {feeder.slot:02d} 取料点超出行程",
                        ref,
                    )
                )

    slots: dict[int, Feeder] = {}
    for feeder in feeders:
        if feeder.slot in slots:
            issues.append(
                ValidationIssue(
                    "error",
                    "DUP_SLOT",
                    f"供料器槽位 {feeder.slot:02d} 被重复占用",
                )
            )
        slots[feeder.slot] = feeder
        if feeder.component_id not in component_map:
            issues.append(
                ValidationIssue(
                    "error",
                    "FEEDER_COMPONENT_MISSING",
                    f"供料器 {feeder.slot:02d} 指向不存在的元件 {feeder.component_id}",
                )
            )

    if not [p for p in product.placements if not p.skip]:
        issues.append(ValidationIssue("error", "NO_ACTIVE", "没有启用的贴装点"))
    return _dedupe_issues(issues)


def _dedupe_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    result: list[ValidationIssue] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        key = (issue.level, issue.code, issue.message)
        if key not in seen:
            result.append(issue)
            seen.add(key)
    return result


def _select_feeder(placement: Placement, feeders: list[Feeder]) -> Feeder | None:
    if placement.feeder_id:
        for feeder in feeders:
            if feeder.id == placement.feeder_id and feeder.enabled:
                return feeder
    candidates = [f for f in feeders if f.component_id == placement.component_id and f.enabled]
    if not candidates:
        return None
    return max(candidates, key=lambda f: (f.remaining, -f.slot))


def _route_nearest_neighbor(steps: list[JobStep], start: Point) -> list[JobStep]:
    """最近邻排序：权重 = 移动到料站 + 料站到贴装点。"""
    remaining = list(steps)
    ordered: list[JobStep] = []
    current = start
    while remaining:
        best_index = 0
        best_score = math.inf
        for i, step in enumerate(remaining):
            score = current.distance_to(step.pick) + step.pick.distance_to(step.place)
            if score < best_score:
                best_score = score
                best_index = i
        chosen = remaining.pop(best_index)
        ordered.append(chosen)
        current = chosen.place
    return [replace(step, index=i) for i, step in enumerate(ordered, start=1)]


def build_job(
    product: Product,
    components: list[Component],
    feeders: list[Feeder],
    limits: MachineLimits,
    optimize: bool = True,
    profile: object | None = None,
    packages: dict[str, object] | None = None,
    alignment: object | None = None,
) -> tuple[JobPlan, list[ValidationIssue]]:
    issues = validate_job(product, components, feeders, limits, alignment=alignment)
    errors = [i for i in issues if i.is_error]
    if errors:
        return (
            JobPlan(
                product_id=product.id,
                product_name=product.name,
                steps=[],
                estimated_cycle_s=0.0,
                optimized=optimize,
            ),
            issues,
        )

    component_map = {c.id: c for c in components}
    steps: list[JobStep] = []
    angle_offset = float(getattr(alignment, "theta_deg", 0.0)) if alignment is not None else 0.0
    for index, placement in enumerate(product.active_placements, start=1):
        component = component_map[placement.component_id]
        feeder = _select_feeder(placement, feeders)
        if feeder is None:  # validate_job 已保证；此处仅静态类型收窄
            continue
        place = machine_point(product, placement, alignment)
        steps.append(
            JobStep(
                index=index,
                refdes=placement.refdes,
                component_id=component.id,
                component_name=component.name,
                nozzle=nozzle_for_component(component, profile, packages),
                feeder_id=feeder.id,
                feeder_slot=feeder.slot,
                pick=Point(feeder.pick_x_mm, feeder.pick_y_mm, feeder.pick_z_mm),
                place=place,
                rotation_deg=(placement.rotation_deg + angle_offset) % 360.0,
                vision_mode=component.vision_mode.value,
            )
        )

    start = Point(0.0, 0.0, limits.safe_z_mm)
    if optimize:
        steps = _route_nearest_neighbor(steps, start)
    else:
        steps = [replace(step, index=i) for i, step in enumerate(steps, start=1)]

    speed = max(20.0, limits.max_speed_mm_s * 0.65)
    total_s = 0.0
    current = start
    for step in steps:
        distance = current.distance_to(step.pick) + step.pick.distance_to(step.place)
        total_s += distance / speed + 0.62
        current = step.place
    plan = JobPlan(
        product_id=product.id,
        product_name=product.name,
        steps=steps,
        estimated_cycle_s=total_s,
        optimized=optimize,
    )
    return plan, issues
