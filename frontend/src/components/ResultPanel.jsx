import { useEffect, useMemo, useState } from "react";
import { diffGroupKeys } from "../lib/geometry";
import RingChart from "./RingChart";
import GroupTable from "./GroupTable";

const STATUS_TEXT = {
  unique: "唯一最优对位",
  ambiguous: "歧义：存在多份最优对位",
  no_solution: "无解",
};

const DIRECTION_TEXT = { forward: "正向", reverse: "反向" };

/** 对位结果：状态横幅 + 指标 + 见证切换 + 环形映射 + 组明细 */
export default function ResultPanel({ result, error, loading, blades, refIntervals, measured }) {
  const [witnessIdx, setWitnessIdx] = useState(0);
  const [hoverGroup, setHoverGroup] = useState(null);
  const [pinnedGroup, setPinnedGroup] = useState(null);
  const [diffMode, setDiffMode] = useState(true);

  // 新结果到达时重置视图状态
  useEffect(() => {
    setWitnessIdx(0);
    setHoverGroup(null);
    setPinnedGroup(null);
  }, [result]);

  const witnesses = result?.witnesses ?? [];
  const witness = witnesses[Math.min(witnessIdx, witnesses.length - 1)] ?? null;
  const other = witnesses.length === 2 ? witnesses[1 - witnessIdx] : null;

  const diffKeys = useMemo(() => {
    if (!diffMode || !witness || !other) return null;
    const { onlyA, onlyB } = diffGroupKeys(witness, other);
    return new Set([...onlyA, ...onlyB]);
  }, [diffMode, witness, other]);

  if (loading) {
    return (
      <div className="result-empty" data-testid="loading">
        <div className="spinner" />
        <p>正在穷举实测环两个方向与全部起点，求解最优对位…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="result-empty">
        <div className="error-box" data-testid="error-box">
          <strong>对位失败</strong>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="result-empty" data-testid="result-empty">
        <div className="placeholder-ring" />
        <p>在左侧导入或编辑参考叶片环、实测间隔、误差限与改动预算，然后发起对位。</p>
        <p className="muted">后端将完整考察实测环的两个方向与全部起点，按 改动数 → 总绝对误差 → 最大组误差 的字典序给出最优规范映射。</p>
      </div>
    );
  }

  const { status, objective, budget } = result;

  return (
    <div className="result" data-testid="result-panel">
      <div className={`status-banner status-${status}`} data-testid="status-banner" data-status={status}>
        <span className="status-title">{STATUS_TEXT[status] ?? status}</span>
        {result.message && <span className="status-msg">{result.message}</span>}
      </div>

      {objective && (
        <div className="stat-grid">
          <div className="stat">
            <span className="stat-label">改动数</span>
            <span className="stat-value" data-testid="stat-mods">{objective.modifications}</span>
          </div>
          <div className="stat">
            <span className="stat-label">总绝对误差</span>
            <span className="stat-value" data-testid="stat-total">{objective.totalAbsError}</span>
          </div>
          <div className="stat">
            <span className="stat-label">最大组误差</span>
            <span className="stat-value" data-testid="stat-max">{objective.maxGroupError}</span>
          </div>
          <div className="stat">
            <span className="stat-label">最优映射数</span>
            <span className="stat-value" data-testid="stat-count">
              {result.optimalMappingCountText ?? String(result.optimalMappingCount)}
            </span>
          </div>
          <div className="stat">
            <span className="stat-label">考察配置</span>
            <span className="stat-value" data-testid="stat-configs">{result.configurationsExamined}</span>
          </div>
          <div className="stat">
            <span className="stat-label">求解耗时</span>
            <span className="stat-value" data-testid="stat-time">{result.computeMs} ms</span>
          </div>
        </div>
      )}

      {objective && (
        <div
          className={`budget-line ${budget.within ? "within" : "over"}`}
          data-testid="budget-line"
        >
          脉冲改动预算：已用 {budget.used} / 上限 {budget.limit}
          {budget.within ? "（在预算内）" : "（超出预算！）"}
        </div>
      )}

      {witnesses.length > 1 && (
        <div className="witness-bar">
          <div className="tabs">
            {witnesses.map((w, i) => (
              <button
                key={w.mappingId}
                data-testid={`witness-tab-${i}`}
                className={`tab ${i === witnessIdx ? "active" : ""}`}
                onClick={() => {
                  setWitnessIdx(i);
                  setPinnedGroup(null);
                  setHoverGroup(null);
                }}
              >
                见证 {String.fromCharCode(65 + i)} · {DIRECTION_TEXT[w.direction]} · 起点 #{w.offset}
              </button>
            ))}
          </div>
          <label className="diff-toggle">
            <input
              type="checkbox"
              data-testid="diff-toggle"
              checked={diffMode}
              onChange={(e) => setDiffMode(e.target.checked)}
            />
            高亮两份见证的差异组
          </label>
        </div>
      )}

      {witness && (
        <>
          <div className="mapping-meta">
            映射 <code data-testid="mapping-id">{witness.mappingId}</code>
            {" · "}行进方向 {DIRECTION_TEXT[witness.direction]}
            {" · "}对齐起点 #{witness.offset}
            {" · "}{witness.groups.length} 组
          </div>
          <RingChart
            blades={blades}
            refIntervals={refIntervals}
            measured={measured}
            witness={witness}
            compareWitness={other}
            diffMode={diffMode && witnesses.length > 1}
            activeGroup={hoverGroup}
            pinnedGroup={pinnedGroup}
            onHoverGroup={setHoverGroup}
            onPinGroup={setPinnedGroup}
          />
          <GroupTable
            witness={witness}
            diffKeys={diffKeys}
            activeGroup={hoverGroup}
            pinnedGroup={pinnedGroup}
            onHoverGroup={setHoverGroup}
            onPinGroup={setPinnedGroup}
          />
        </>
      )}

      {status === "no_solution" && (
        <p className="hint" data-testid="no-solution-hint">
          可尝试放宽误差限，或检查实测数据是否存在系统性漏检 / 周长录入错误。
        </p>
      )}
    </div>
  );
}
