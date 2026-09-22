// 环形图几何与见证对比工具

export const TAU = Math.PI * 2;

/** 前缀和：[0, v0, v0+v1, ...]，长度 = values.length + 1 */
export function prefixSums(values) {
  const out = [0];
  for (const v of values) out.push(out[out.length - 1] + v);
  return out;
}

/** 周长比例 → 角度（0 点在正上方，顺时针增大） */
export function angleAt(frac) {
  return -Math.PI / 2 + frac * TAU;
}

export function polar(cx, cy, r, angle) {
  return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
}

/** SVG 圆弧路径（a0 → a1，顺时针；自动处理整圆） */
export function arcPath(cx, cy, r, a0, a1) {
  let span = a1 - a0;
  if (span <= 0) return "";
  if (span >= TAU - 1e-9) {
    // 整圆：拆成两个半圆
    const mid = a0 + span / 2;
    return arcPath(cx, cy, r, a0, mid) + " " + arcPath(cx, cy, r, mid, a1);
  }
  const [x0, y0] = polar(cx, cy, r, a0);
  const [x1, y1] = polar(cx, cy, r, a1);
  const large = span > Math.PI ? 1 : 0;
  return `M ${x0.toFixed(3)} ${y0.toFixed(3)} A ${r} ${r} 0 ${large} 1 ${x1.toFixed(3)} ${y1.toFixed(3)}`;
}

/** 组的规范键：用于跨见证比较 */
export function groupKey(g) {
  return `${g.refStart}+${g.refCount}@${g.measIndices.join(".")}`;
}

/** 两份见证的组键差集 */
export function diffGroupKeys(wA, wB) {
  const setA = new Set(wA.groups.map(groupKey));
  const setB = new Set(wB.groups.map(groupKey));
  const onlyA = new Set([...setA].filter((k) => !setB.has(k)));
  const onlyB = new Set([...setB].filter((k) => !setA.has(k)));
  return { onlyA, onlyB };
}

/**
 * 实测侧一组脉冲（原始下标，循环连续，可能绕环）在周长上的
 * 起止比例。cum 为实测间隔前缀和。
 */
export function measArcFractions(indices, cum) {
  const m = cum.length - 1;
  const total = cum[m];
  const set = new Set(indices);
  // 起点：其前驱不在组内的那个下标（循环连续序列恰有一个）
  let startIdx = indices[0];
  for (const i of indices) {
    if (!set.has((i - 1 + m) % m)) {
      startIdx = i;
      break;
    }
  }
  const span = indices.reduce((acc, i) => acc + (cum[i + 1] - cum[i]), 0);
  const start = cum[startIdx] / total;
  return { start, end: (cum[startIdx] + span) / total };
}
