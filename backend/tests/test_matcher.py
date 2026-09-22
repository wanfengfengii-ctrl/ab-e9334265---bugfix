"""求解器测试：手工案例 + 与指数级暴力枚举的随机对照。"""

from __future__ import annotations

import itertools
import random

import pytest

from app.matcher import (
    MAX_SPAN,
    Objective,
    Witness,
    _aligned_indices,
    solve,
)


# ---------------------------------------------------------------------------
# 暴力枚举（仅用于小规模对照）
# ---------------------------------------------------------------------------

def _compositions(total: int, parts: int):
    """把 total 拆成 parts 个 1..MAX_SPAN 的组（递归枚举）。"""
    if parts == 0:
        if total == 0:
            yield ()
        return
    for first in range(1, MAX_SPAN + 1):
        rem = total - first
        if rem < (parts - 1) * 1 or rem > (parts - 1) * MAX_SPAN:
            continue
        for rest in _compositions(rem, parts - 1):
            yield (first,) + rest


def brute_force(ref: list[int], meas: list[int], tolerance: int):
    """指数级穷举所有方向/起点/切分，返回 (最优目标或 None, 最优映射数精确值)。"""
    n, m = len(ref), len(meas)
    best: tuple[int, int, int] | None = None
    count = 0
    for direction in ("forward", "reverse"):
        for offset in range(m):
            idx = _aligned_indices(direction, offset, m)
            vals = [meas[t] for t in idx]
            pm = [0]
            for v in vals:
                pm.append(pm[-1] + v)
            pr = [0]
            for v in ref:
                pr.append(pr[-1] + v)
            k_min = max(-(-n // MAX_SPAN), -(-m // MAX_SPAN))
            for k in range(k_min, min(n, m) + 1):
                for comp_r in _compositions(n, k):
                    bounds_r = [0]
                    for a in comp_r:
                        bounds_r.append(bounds_r[-1] + a)
                    sums_r = [pr[bounds_r[t + 1]] - pr[bounds_r[t]] for t in range(k)]
                    for comp_m in _compositions(m, k):
                        bounds_m = [0]
                        for b in comp_m:
                            bounds_m.append(bounds_m[-1] + b)
                        errs = [
                            abs(sums_r[t] - (pm[bounds_m[t + 1]] - pm[bounds_m[t]]))
                            for t in range(k)
                        ]
                        if any(e > tolerance for e in errs):
                            continue
                        obj = (
                            sum(a - 1 for a in comp_r) + sum(b - 1 for b in comp_m),
                            sum(errs),
                            max(errs),
                        )
                        if best is None or obj < best:
                            best, count = obj, 1
                        elif obj == best:
                            count += 1
    return best, count


def _check_against_brute(ref, meas, tolerance):
    expected_obj, expected_count = brute_force(ref, meas, tolerance)
    result = solve(ref, meas, tolerance)
    if expected_obj is None:
        assert result.status == "no_solution"
        assert result.witnesses == []
        return
    assert result.status == ("unique" if expected_count == 1 else "ambiguous")
    assert result.objective is not None
    assert result.objective.as_tuple() == expected_obj
    assert result.optimal_count == expected_count
    # 见证自身必须达到最优目标
    for w in result.witnesses:
        assert w.objective.as_tuple() == expected_obj
        _validate_witness(w, ref, meas, tolerance)
    if result.status == "ambiguous":
        assert len(result.witnesses) == 2
        assert result.witnesses[0].mapping_id() != result.witnesses[1].mapping_id()
    else:
        assert len(result.witnesses) == 1


def _validate_witness(w: Witness, ref, meas, tolerance):
    n, m = len(ref), len(meas)
    # 参考侧完整覆盖且连续
    assert [g.ref_start for g in w.groups] == list(
        itertools.accumulate([0] + [g.ref_count for g in w.groups[:-1]])
    )
    assert sum(g.ref_count for g in w.groups) == n
    # 实测侧：沿行进方向连续且完整覆盖
    idx = _aligned_indices(w.direction, w.offset, m)
    flat = [t for g in w.groups for t in g.meas_indices]
    assert flat == idx
    for g in w.groups:
        assert 1 <= g.ref_count <= MAX_SPAN
        assert 1 <= len(g.meas_indices) <= MAX_SPAN
        assert g.ref_sum == sum(ref[g.ref_start : g.ref_start + g.ref_count])
        assert g.meas_sum == sum(meas[t] for t in g.meas_indices)
        assert g.abs_error <= tolerance


# ---------------------------------------------------------------------------
# 手工案例
# ---------------------------------------------------------------------------

def test_unique_with_missed_pulse():
    ref = [50, 52, 48, 51, 49, 53, 47, 55, 45, 49, 51, 50]
    meas = [50, 100, 51, 49, 53, 47, 55, 45, 49, 51, 50]  # 52+48 漏检合并
    r = solve(ref, meas, 2)
    assert r.status == "unique"
    assert r.objective == Objective(1, 0, 0)
    w = r.witnesses[0]
    assert (w.direction, w.offset) == ("forward", 0)
    merged = [g for g in w.groups if g.modifications]
    assert len(merged) == 1
    assert merged[0].ref_count == 2 and len(merged[0].meas_indices) == 1
    assert merged[0].ref_sum == 100 and merged[0].meas_sum == 100


def test_ambiguous_repeated_intervals():
    ref = [40, 40, 55] * 4
    r = solve(ref, list(ref), 1)
    assert r.status == "ambiguous"
    assert r.objective == Objective(0, 0, 0)
    assert r.optimal_count >= 2
    assert len(r.witnesses) == 2
    ids = {w.mapping_id() for w in r.witnesses}
    assert len(ids) == 2


def test_no_solution_tolerance_too_tight():
    r = solve([50] * 12, [53, 53, 53, 41] * 3, 1)
    assert r.status == "no_solution"
    assert r.witnesses == []


def test_structural_no_solution():
    # 13 个参考间隔 vs 4 个实测间隔：每组至多 3 个，无法分组
    r = solve([10] * 13, [32, 33, 32, 33], 1000)
    assert r.status == "no_solution"


def test_modifications_beat_error():
    # 1-1 对位误差 (1,1)；合并对位误差 0 但改动 2 —— 改动数优先
    r = solve([8, 8], [9, 7], 5)
    assert r.objective == Objective(0, 2, 1)


def test_total_error_breaks_tie():
    # 两种改动数相同的方案：总误差小者胜
    r = solve([10, 3, 10], [11, 12], 2)
    assert r.objective == Objective(1, 2, 1)


def test_max_error_breaks_tie():
    # 改动数与总误差相同的两个可行解：(1, 8, 3) 与 (1, 8, 4)，
    # 第三关键字（最大组误差）应决定胜负
    ref, meas = [7, 7, 9, 3, 3], [9, 9, 9, 2]
    r = solve(ref, meas, 5)
    assert r.objective == Objective(1, 8, 3)
    assert r.objective.as_tuple() == brute_force(ref, meas, 5)[0]


def test_reverse_direction_detected():
    ref = [50, 52, 48, 51, 49, 53, 47, 55, 45, 49, 51, 50]
    r = solve(ref, list(reversed(ref)), 0)
    assert r.status == "unique"
    assert r.witnesses[0].direction == "reverse"


def test_offset_rotation_detected():
    ref = [50, 52, 48, 51, 49, 53, 47, 55, 45, 49, 51, 50]
    meas = ref[4:] + ref[:4]  # 循环平移：ref[0] 落在 meas[8]
    r = solve(ref, meas, 0)
    assert r.status == "unique"
    assert r.objective == Objective(0, 0, 0)
    assert r.witnesses[0].offset == 8


def test_witness_canonical_stable():
    ref = [50, 52, 48, 51, 49, 53, 47, 55, 45, 49, 51, 50]
    meas = [50, 100, 51, 49, 53, 47, 55, 45, 49, 51, 50]
    r1 = solve(ref, meas, 2)
    r2 = solve(ref, meas, 2)
    assert r1.witnesses[0].mapping_id() == r2.witnesses[0].mapping_id()


def test_ambiguous_same_config_two_witnesses():
    # 同一 (方向, 起点) 下存在两种最优切分
    # ref = [4, 4, 4, 4]，meas = [8, 8]，tol=0：
    #   切法一 (4,4)|(4,4) 与切法二相同…… 需要非对称数据：
    # ref = [3, 5, 3, 5]，meas = [8, 8]：两种切分都误差 0、改动 2
    r = solve([3, 5, 3, 5], [8, 8], 0)
    assert r.status == "ambiguous"
    assert r.optimal_count >= 2
    assert len(r.witnesses) == 2
    assert r.witnesses[0].mapping_id() != r.witnesses[1].mapping_id()


def test_ambiguous_within_single_config():
    # 全局仅一个最优配置（反向、起点 2），但其内部存在两种最优切分：
    # 验证同配置分叉重构路径
    ref = [8, 3, 8, 6, 6, 2]
    meas = [7, 9, 9, 2, 6]
    r = solve(ref, meas, 2)
    assert r.status == "ambiguous"
    assert r.objective == Objective(1, 4, 2)
    assert r.optimal_count == 2
    assert len(r.witnesses) == 2
    w1, w2 = r.witnesses
    # 两份见证来自同一配置，但规范映射不同
    assert (w1.direction, w1.offset) == (w2.direction, w2.offset) == ("reverse", 2)
    assert w1.mapping_id() != w2.mapping_id()
    for w in (w1, w2):
        assert w.objective == Objective(1, 4, 2)


# ---------------------------------------------------------------------------
# 随机对照：DP vs 暴力枚举
# ---------------------------------------------------------------------------

def _random_case(rng: random.Random):
    n = rng.randint(3, 7)
    m = rng.randint(3, 7)
    ref = [rng.randint(1, 7) for _ in range(n)]
    # 构造等周长实测环：先随机再补差
    meas = [rng.randint(1, 7) for _ in range(m - 1)]
    last = sum(ref) - sum(meas)
    if last < 1:
        meas.append(1)
        ref[0] += 1 - last
    else:
        meas.append(last)
    tolerance = rng.randint(0, 4)
    return ref, meas, tolerance


@pytest.mark.parametrize("seed", range(60))
def test_against_brute_force(seed: int):
    rng = random.Random(10_000 + seed)
    ref, meas, tolerance = _random_case(rng)
    _check_against_brute(ref, meas, tolerance)
