"""叶尖脉冲环对位核心求解器。

问题模型
--------
参考叶片环与实测脉冲环都被解释为循环序列（单位：相邻脉冲/叶片间隔）。
一次对位把两个环分别切成数量相同的连续非空组：

* 每组任一侧至多包含 ``MAX_SPAN`` 个间隔；
* 组内两侧间隔和之差（绝对误差）不得超过误差限；
* 一组的改动数 = 两侧各自超出一个间隔的数量之和，即 ``(a-1) + (b-1)``，
  其中 a、b 分别为该组参考侧与实测侧的间隔数。总改动数 = n + m - 2k
  （k 为组数），因此最小化改动数等价于最大化组数。

目标按字典序依次最小化：改动数 → 总绝对误差 → 最大组误差。

求解策略
--------
固定参考环起点（叶片编号是绝对坐标），完整枚举实测环的两个方向与全部
m 个起点，共 2m 个候选配置。对每个配置做分组动态规划；所有配置的 DP
以 numpy 向量化方式批量推进（按参考环前缀逐行滚动，每行对所有配置与
实测位置同时求字典序最优），并同步维护最优路径计数，从而判定最优规范
映射唯一、歧义还是无解。计数必须精确：快速路径以 int64 推进并在
``_COUNT_SAT`` 处饱和探测，一旦触及阈值即以 Python 任意精度整数重算，
因此任意规模输入的最优映射数都是精确值（可超出 int64 / JS 安全整数）。

规范映射
--------
一个对位映射由 ``(方向, 起点, 各组切分)`` 完全确定，三者即为其规范形式；
不同的 DP 路径与不同的规范映射一一对应，因此最优路径计数就是最优映射数。
歧义时返回两份规范形式不同的最优见证，供前端逐组对比高亮。
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

import numpy as np

MAX_SPAN = 3            # 每组任一侧至多 3 个间隔
_COUNT_SAT = (1 << 62) - 1  # int64 计数饱和探测阈值：达到即触发任意精度重算
_INF = 1 << 50          # 不可达代价
_BIG_ERR = 1 << 40      # 非法组误差占位（远大于任何合法误差限）


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Objective:
    """字典序比较的三元目标。"""

    modifications: int
    total_abs_error: int
    max_group_error: int

    def as_tuple(self) -> tuple[int, int, int]:
        return (self.modifications, self.total_abs_error, self.max_group_error)


@dataclass
class Group:
    """一个对位组：参考侧连续若干间隔 ↔ 实测侧连续若干间隔。"""

    index: int                 # 组序号（沿参考环正向）
    ref_start: int             # 参考侧首个间隔下标（0 起）
    ref_count: int             # 参考侧间隔数（1..3）
    meas_indices: list[int]    # 实测脉冲间隔的原始下标（按对齐行进方向排列）
    ref_sum: int
    meas_sum: int

    @property
    def abs_error(self) -> int:
        return abs(self.ref_sum - self.meas_sum)

    @property
    def modifications(self) -> int:
        return (self.ref_count - 1) + (len(self.meas_indices) - 1)


@dataclass
class Witness:
    """一份完整对位见证（一个规范映射）。"""

    direction: str             # "forward" | "reverse"
    offset: int                # 与参考环起点对齐的实测间隔原始下标
    groups: list[Group] = field(default_factory=list)

    @property
    def objective(self) -> Objective:
        return Objective(
            modifications=sum(g.modifications for g in self.groups),
            total_abs_error=sum(g.abs_error for g in self.groups),
            max_group_error=max((g.abs_error for g in self.groups), default=0),
        )

    def canonical(self) -> str:
        """规范形式：方向、起点与全部切分唯一决定该映射。"""
        parts = [f"{self.direction}:{self.offset}"]
        for g in self.groups:
            parts.append(
                f"r{g.ref_start}+{g.ref_count}m{','.join(map(str, g.meas_indices))}"
            )
        return "|".join(parts)

    def mapping_id(self) -> str:
        return hashlib.sha1(self.canonical().encode("utf-8")).hexdigest()[:12]


@dataclass
class SolveResult:
    status: str                # "unique" | "ambiguous" | "no_solution"
    objective: Objective | None
    witnesses: list[Witness]
    optimal_count: int         # 最优规范映射数（精确值，可超出 int64）
    configurations: int        # 实际考察的配置数（2m）
    message: str | None = None


# ---------------------------------------------------------------------------
# 配置空间：方向 × 起点
# ---------------------------------------------------------------------------

def _config_params(config: int, m: int) -> tuple[str, int]:
    """把向量化配置下标翻译成 (方向, 起点)。

    前 m 个配置为正向：起点 offset = config。
    后 m 个配置为反向：对反转后的实测序列做旋转，第 t 个旋转对应
    原始下标起点 offset = (m - 1 - t) mod m，即沿反向行进
    ``offset, offset-1, ..., offset-m+1``。
    """
    if config < m:
        return ("forward", config)
    t = config - m
    return ("reverse", (m - 1 - t) % m)


def _aligned_indices(direction: str, offset: int, m: int) -> list[int]:
    """对齐后实测间隔的原始下标序列（沿行进方向）。"""
    if direction == "forward":
        return [(offset + j) % m for j in range(m)]
    return [(offset - j) % m for j in range(m)]


# ---------------------------------------------------------------------------
# 向量化分组 DP（所有配置一次性推进）
# ---------------------------------------------------------------------------

def _aligned_prefix_sums(meas: list[int], m: int) -> np.ndarray:
    """返回形状 (2m, m+1) 的前缀和矩阵：PS[c, j] 为配置 c 前 j 个间隔之和。"""
    M = np.asarray(meas, dtype=np.int64)
    out = np.empty((2 * m, m + 1), dtype=np.int64)
    rotations = np.arange(m)[:, None]
    steps = np.arange(m + 1)[None, :]
    for block, seq in ((0, np.concatenate([M, M])),
                       (m, np.concatenate([M[::-1], M[::-1]]))):
        prefix = np.zeros(2 * m + 1, dtype=np.int64)
        np.cumsum(seq, out=prefix[1:])
        out[block:block + m] = prefix[rotations + steps] - prefix[rotations]
    return out


def _dp_all_configs(
    ref: list[int], meas: list[int], tolerance: int, exact: bool = False
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """对所有 2m 个配置同时做分组 DP，返回最后一行的代价与计数数组。

    dp[i][j]：参考环前 i 个间隔与（某配置下）实测环前 j 个间隔对齐的
    最优字典序代价 (改动数, 总绝对误差, 最大组误差) 及最优路径计数。
    转移枚举最后一组两侧的跨度 (a, b) ∈ {1,2,3}²。

    ``exact=False``（快速路径）：计数为 int64，并在 ``_COUNT_SAT`` 处饱和
    —— 低于阈值的计数是精确的，达到阈值仅表示“需要任意精度重算”。
    阈值取 (1<<62)-1：饱和值相加不溢出 int64。
    ``exact=True``：计数使用 Python 任意精度整数（object 数组），结果精确。
    """
    n, m = len(ref), len(meas)
    S = 2 * m
    PS = _aligned_prefix_sums(meas, m)

    # 实测侧分组和：G[b][c, j] = 配置 c 下第 j-b..j-1 个间隔之和（j < b 时为 -1）
    G = []
    for b in (1, 2, 3):
        Gb = np.full((S, m + 1), -1, dtype=np.int64)
        Gb[:, b:] = PS[:, b:] - PS[:, :-b]
        G.append(Gb)

    PR = np.zeros(n + 1, dtype=np.int64)
    np.cumsum(np.asarray(ref, dtype=np.int64), out=PR[1:])

    cnt_dtype = object if exact else np.int64

    def _blank_row() -> list[np.ndarray]:
        return [np.full((S, m + 1), _INF, dtype=np.int64) for _ in range(3)] + \
               [np.zeros((S, m + 1), dtype=cnt_dtype)]

    rows = [_blank_row() for _ in range(MAX_SPAN + 1)]
    rows[0][0][:, 0] = 0  # 基础情形 dp[0][0] = (0, 0, 0)，计数 1
    rows[0][1][:, 0] = 0
    rows[0][2][:, 0] = 0
    rows[0][3][:, 0] = 1

    for i in range(1, n + 1):
        cur = rows[i % (MAX_SPAN + 1)]
        for arr in cur[:3]:
            arr.fill(_INF)
        cur[3].fill(0)

        # 列窗口：由每组 1..3 个间隔的结构性约束剪枝
        lo = max((i + MAX_SPAN - 1) // MAX_SPAN, m - MAX_SPAN * (n - i), 1)
        hi = min(MAX_SPAN * i, m - (n - i + MAX_SPAN - 1) // MAX_SPAN)
        if lo > hi:
            continue

        for a in (1, 2, 3):
            if a > i:
                break
            prev = rows[(i - a) % (MAX_SPAN + 1)]
            ref_sum = int(PR[i] - PR[i - a])
            for b in (1, 2, 3):
                jlo = max(lo, b)  # j < b 时组不存在，直接排除
                if jlo > hi:
                    continue
                js = slice(jlo, hi + 1)
                src = slice(jlo - b, hi + 1 - b)
                c_mods, c_tot = cur[0][:, js], cur[1][:, js]
                c_max, c_cnt = cur[2][:, js], cur[3][:, js]

                Gb = G[b - 1][:, js]
                err = np.abs(ref_sum - Gb)
                np.copyto(err, _BIG_ERR, where=Gb < 0)  # 防御：非法组
                ok = err <= tolerance
                ok &= prev[0][:, src] < _INF            # 前驱可达
                if not ok.any():
                    continue

                n_mods = prev[0][:, src] + (a + b - 2)
                n_tot = prev[1][:, src] + err
                n_max = np.maximum(prev[2][:, src], err)
                n_cnt = prev[3][:, src]
                np.minimum(n_mods, _INF, out=n_mods)    # 截断防溢出
                np.minimum(n_tot, _INF, out=n_tot)

                better = ok & (
                    (n_mods < c_mods)
                    | ((n_mods == c_mods) & (n_tot < c_tot))
                    | ((n_mods == c_mods) & (n_tot == c_tot) & (n_max < c_max))
                )
                tied = ok & ~better & (n_mods == c_mods) & (n_tot == c_tot) & (n_max == c_max)

                np.copyto(c_mods, n_mods, where=better)
                np.copyto(c_tot, n_tot, where=better)
                np.copyto(c_max, n_max, where=better)
                np.copyto(c_cnt, n_cnt, where=better)
                if tied.any():
                    if exact:
                        np.copyto(c_cnt, c_cnt + n_cnt, where=tied)
                    else:
                        np.copyto(c_cnt, np.minimum(c_cnt + n_cnt, _COUNT_SAT), where=tied)

    return rows[n % (MAX_SPAN + 1)]


# ---------------------------------------------------------------------------
# 见证重构（单配置标量 DP + 回溯）
# ---------------------------------------------------------------------------

def _scalar_dp(ref: list[int], vals: list[int], tolerance: int):
    """单配置完整 DP 网格，供回溯使用。vals 为对齐后的实测间隔序列。"""
    n, m = len(ref), len(vals)
    PR = [0] * (n + 1)
    for i, v in enumerate(ref):
        PR[i + 1] = PR[i] + v
    PM = [0] * (m + 1)
    for j, v in enumerate(vals):
        PM[j + 1] = PM[j] + v

    dp: list[list[tuple[int, int, int] | None]] = \
        [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = (0, 0, 0)
    for i in range(n + 1):
        for j in range(m + 1):
            if i == 0 and j == 0:
                continue
            best = None
            for a in (1, 2, 3):
                if a > i:
                    break
                rs = PR[i] - PR[i - a]
                for b in (1, 2, 3):
                    if b > j:
                        break
                    err = abs(rs - (PM[j] - PM[j - b]))
                    if err > tolerance:
                        continue
                    prev = dp[i - a][j - b]
                    if prev is None:
                        continue
                    cand = (prev[0] + a + b - 2, prev[1] + err, max(prev[2], err))
                    if best is None or cand < best:
                        best = cand
            dp[i][j] = best
    return dp, PR, PM


def _optimal_transitions(dp, PR, PM, tolerance, i, j) -> list[tuple[int, int]]:
    """单元 (i, j) 的全部最优转移（保持确定性的枚举顺序）。"""
    best = dp[i][j]
    out = []
    for a in (1, 2, 3):
        if a > i:
            break
        rs = PR[i] - PR[i - a]
        for b in (1, 2, 3):
            if b > j:
                break
            err = abs(rs - (PM[j] - PM[j - b]))
            if err > tolerance:
                continue
            prev = dp[i - a][j - b]
            if prev is None:
                continue
            cand = (prev[0] + a + b - 2, prev[1] + err, max(prev[2], err))
            if cand == best:
                out.append((a, b))
    return out


def _reconstruct(
    ref: list[int],
    meas: list[int],
    tolerance: int,
    direction: str,
    offset: int,
    diverge_from: Witness | None = None,
) -> Witness | None:
    """重构一份最优见证。

    给定 ``diverge_from`` 时，在同一配置内寻找一条与其规范形式不同的
    最优路径（沿对方路径回溯，在最后一个存在备选最优转移的单元处分叉）。
    """
    n, m = len(ref), len(meas)
    idx = _aligned_indices(direction, offset, m)
    vals = [meas[t] for t in idx]
    dp, PR, PM = _scalar_dp(ref, vals, tolerance)
    if dp[n][m] is None:
        return None

    avoid: dict[tuple[int, int], tuple[int, int]] = {}
    if diverge_from is not None:
        ci = cj = 0
        for g in diverge_from.groups:
            ci += g.ref_count
            cj += len(g.meas_indices)
            avoid[(ci, cj)] = (g.ref_count, len(g.meas_indices))

    path = []
    i, j = n, m
    diverged = diverge_from is None
    while i > 0 or j > 0:
        opts = _optimal_transitions(dp, PR, PM, tolerance, i, j)
        if not opts:
            return None
        if not diverged:
            banned = avoid.get((i, j))
            alts = [t for t in opts if t != banned]
            if alts:
                choice = alts[0]
                diverged = True
            elif banned in opts:
                choice = banned
            else:  # 防御：理论不应出现
                choice = opts[0]
        else:
            choice = opts[0]
        a, b = choice
        path.append((i, j, a, b))
        i -= a
        j -= b
    if not diverged:
        return None
    path.reverse()

    groups = []
    for end_i, end_j, a, b in path:
        groups.append(Group(
            index=len(groups),
            ref_start=end_i - a,
            ref_count=a,
            meas_indices=idx[end_j - b:end_j],
            ref_sum=PR[end_i] - PR[end_i - a],
            meas_sum=PM[end_j] - PM[end_j - b],
        ))
    return Witness(direction=direction, offset=offset, groups=groups)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def solve(ref: list[int], meas: list[int], tolerance: int) -> SolveResult:
    """完整考察两个方向与全部起点，返回最优对位结果。"""
    n, m = len(ref), len(meas)
    # m ≤ 2 时反向配置与正向逐一同效（序列相同），仅考察正向以避免重复计数
    configurations = 2 * m if m > 2 else m

    min_groups = max(math.ceil(n / MAX_SPAN), math.ceil(m / MAX_SPAN))
    if min_groups > min(n, m):
        return SolveResult(
            status="no_solution",
            objective=None,
            witnesses=[],
            optimal_count=0,
            configurations=configurations,
            message="间隔数量差异过大：每组至多 3 个间隔，结构上无法完成分组",
        )

    mods, tot, mx, cnt = _dp_all_configs(ref, meas, tolerance)
    col = m
    candidate_configs = range(configurations)
    reachable = [c for c in candidate_configs if mods[c, col] < _INF]
    if not reachable:
        return SolveResult(
            status="no_solution",
            objective=None,
            witnesses=[],
            optimal_count=0,
            configurations=configurations,
            message="在给定误差限内不存在满足约束的对位方案",
        )

    best = min((int(mods[c, col]), int(tot[c, col]), int(mx[c, col])) for c in reachable)
    best_configs = [c for c in reachable
                    if (int(mods[c, col]), int(tot[c, col]), int(mx[c, col])) == best]
    optimal_count = 0
    saturated = False
    for c in best_configs:
        optimal_count += int(cnt[c, col])
        if optimal_count >= _COUNT_SAT:
            saturated = True
            break
    if saturated:
        # int64 快速路径触及饱和阈值：代价 DP 确定性一致，直接以任意精度
        # 整数重算计数，保证最优映射数精确（可超出 int64 / JS 安全整数）。
        _, _, _, cnt_exact = _dp_all_configs(ref, meas, tolerance, exact=True)
        optimal_count = sum(int(cnt_exact[c, col]) for c in best_configs)

    objective = Objective(*best)
    status = "unique" if optimal_count == 1 else "ambiguous"

    # 确定性排序：先方向（正向优先）后起点，保证见证选择可复现
    best_configs.sort(key=lambda c: (0 if c < m else 1, _config_params(c, m)[1]))

    witnesses: list[Witness] = []
    first = _reconstruct(ref, meas, tolerance, *_config_params(best_configs[0], m))
    if first is not None:
        witnesses.append(first)

    if status == "ambiguous":
        second: Witness | None = None
        if len(best_configs) >= 2:
            second = _reconstruct(ref, meas, tolerance, *_config_params(best_configs[1], m))
        if second is None and first is not None:
            second = _reconstruct(ref, meas, tolerance, *_config_params(best_configs[0], m),
                                  diverge_from=first)
        if second is not None and second.mapping_id() != first.mapping_id():
            witnesses.append(second)
        elif second is None and first is None:
            status = "no_solution"

    # 防御：规范形式应互不相同；若异常退化则按唯一处理
    if len(witnesses) == 2 and witnesses[0].mapping_id() == witnesses[1].mapping_id():
        witnesses.pop()
        status = "unique"

    message = None
    if status == "ambiguous":
        message = f"存在 {optimal_count} 份最优规范映射，对位歧义"
    elif status == "unique":
        message = "最优规范映射唯一"

    return SolveResult(
        status=status,
        objective=objective,
        witnesses=witnesses,
        optimal_count=optimal_count,
        configurations=configurations,
        message=message,
    )
