import { useMemo } from "react";
import {
  angleAt,
  arcPath,
  diffGroupKeys,
  groupKey,
  measArcFractions,
  polar,
  prefixSums,
} from "../lib/geometry";

const SIZE = 620;
const C = SIZE / 2;
const R_REF_TRACK = 244; // 参考环轨道
const R_GREF = 222;      // 组弧（参考侧）
const R_GMEAS = 194;     // 组弧（实测侧）
const R_MEAS_TRACK = 172; // 实测环轨道
const R_BLADE_LABEL = 266;
const R_PULSE_LABEL = 148;

const PALETTE = [
  "#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#db2777",
  "#65a30d", "#9333ea", "#0d9488", "#e11d48", "#4f46e5", "#a16207", "#0284c7",
];
const SHARED_GRAY = "#94a3b8";

/**
 * 环形映射图：外环为参考叶片，内环为实测脉冲；
 * 每个对位组以同色双弧 + 边界连线表示。
 */
export default function RingChart({
  blades,
  refIntervals,
  measured,
  witness,
  compareWitness,
  diffMode,
  activeGroup,
  pinnedGroup,
  onHoverGroup,
  onPinGroup,
}) {
  const n = refIntervals.length;
  const m = measured.length;
  const cumR = useMemo(() => prefixSums(refIntervals), [refIntervals]);
  const cumM = useMemo(() => prefixSums(measured), [measured]);
  const total = cumR[n];

  const diffKeys = useMemo(() => {
    if (!diffMode || !compareWitness) return null;
    const { onlyA, onlyB } = diffGroupKeys(witness, compareWitness);
    return new Set([...onlyA, ...onlyB]);
  }, [diffMode, witness, compareWitness]);

  const bladeLabelEvery = Math.max(1, Math.ceil(n / 48));
  const pulseLabelEvery = Math.max(1, Math.ceil(m / 48));
  const effective = activeGroup ?? pinnedGroup;

  const groupShapes = witness.groups.map((g, i) => {
    const a0 = angleAt(cumR[g.refStart] / total);
    const a1 = angleAt((cumR[g.refStart] + g.refSum) / total);
    const span = measArcFractions(g.measIndices, cumM);
    const b0 = angleAt(span.start);
    const b1 = angleAt(span.end);
    const isDiff = diffKeys ? diffKeys.has(groupKey(g)) : false;
    const color = diffKeys ? (isDiff ? PALETTE[i % PALETTE.length] : SHARED_GRAY) : PALETTE[i % PALETTE.length];
    const dim = effective != null && effective !== i;
    return { g, i, a0, a1, b0, b1, color, isDiff, dim };
  });

  return (
    <div className="ring-wrap">
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="ring-chart"
        data-testid="ring-chart"
        role="img"
        aria-label="环形对位映射图"
      >
        {/* 轨道 */}
        <circle cx={C} cy={C} r={R_REF_TRACK} className="track" />
        <circle cx={C} cy={C} r={R_MEAS_TRACK} className="track" />

        {/* 组弧与边界连线 */}
        {groupShapes.map(({ g, i, a0, a1, b0, b1, color, isDiff, dim }) => {
          const cls = `group-arc${dim ? " dim" : ""}${isDiff ? " is-diff" : ""}${
            effective === i ? " active" : ""
          }`;
          const [rx0, ry0] = polar(C, C, R_GREF, a0);
          const [mx0, my0] = polar(C, C, R_GMEAS, b0);
          const [rx1, ry1] = polar(C, C, R_GREF, a1);
          const [mx1, my1] = polar(C, C, R_GMEAS, b1);
          return (
            <g
              key={i}
              className={cls}
              data-group-index={i}
              onMouseEnter={() => onHoverGroup(i)}
              onMouseLeave={() => onHoverGroup(null)}
              onClick={() => onPinGroup(pinnedGroup === i ? null : i)}
            >
              <path d={arcPath(C, C, R_GREF, a0, a1)} stroke={color} className="group-arc-ref" data-group-index={i} />
              <path d={arcPath(C, C, R_GMEAS, b0, b1)} stroke={color} className="group-arc-meas" data-group-index={i} />
              <line x1={rx0} y1={ry0} x2={mx0} y2={my0} stroke={color} className="group-link" />
              <line x1={rx1} y1={ry1} x2={mx1} y2={my1} stroke={color} className="group-link" />
            </g>
          );
        })}

        {/* 叶片刻度与编号 */}
        {blades.map((b, i) => {
          const ang = angleAt(cumR[i] / total);
          const [x0, y0] = polar(C, C, R_REF_TRACK - 7, ang);
          const [x1, y1] = polar(C, C, R_REF_TRACK + 7, ang);
          const [lx, ly] = polar(C, C, R_BLADE_LABEL, ang);
          return (
            <g key={`b${i}`}>
              <line x1={x0} y1={y0} x2={x1} y2={y1} className="tick blade-tick" />
              {i % bladeLabelEvery === 0 && (
                <text x={lx} y={ly} className="blade-label" textAnchor="middle" dominantBaseline="middle">
                  {b}
                </text>
              )}
            </g>
          );
        })}

        {/* 脉冲刻度与序号 */}
        {measured.map((_, j) => {
          const ang = angleAt(cumM[j] / total);
          const [x0, y0] = polar(C, C, R_MEAS_TRACK - 6, ang);
          const [x1, y1] = polar(C, C, R_MEAS_TRACK + 6, ang);
          const [lx, ly] = polar(C, C, R_PULSE_LABEL, ang);
          return (
            <g key={`p${j}`}>
              <line x1={x0} y1={y0} x2={x1} y2={y1} className="tick pulse-tick" />
              {j % pulseLabelEvery === 0 && (
                <text x={lx} y={ly} className="pulse-label" textAnchor="middle" dominantBaseline="middle">
                  #{j}
                </text>
              )}
            </g>
          );
        })}

        {/* 中心摘要 */}
        <text x={C} y={C - 14} className="center-main" textAnchor="middle" data-testid="ring-center">
          周长 {total}
        </text>
        <text x={C} y={C + 10} className="center-sub" textAnchor="middle">
          {witness.groups.length} 组 · 改动 {witness.groups.reduce((s, g) => s + g.modifications, 0)}
        </text>
        <text x={C} y={C + 30} className="center-sub" textAnchor="middle">
          {witness.direction === "forward" ? "正向" : "反向"} · 起点 #{witness.offset}
        </text>
      </svg>
      <div className="legend">
        <span><i className="swatch swatch-ref" /> 外环：参考叶片（{n}）</span>
        <span><i className="swatch swatch-meas" /> 内环：实测脉冲（{m}）</span>
        <span><i className="swatch swatch-group" /> 同色双弧：一个对位组</span>
        {diffKeys && <span><i className="swatch swatch-shared" /> 灰色：两份见证一致的组</span>}
      </div>
    </div>
  );
}
