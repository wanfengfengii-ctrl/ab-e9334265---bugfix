/** 误差限与脉冲改动预算 */

export default function ParamsPanel({ tolerance, budget, onTolerance, onBudget }) {
  return (
    <section className="editor" data-testid="params-panel">
      <div className="editor-head">
        <h2>对位参数</h2>
      </div>
      <div className="param-grid">
        <label className="param">
          <span className="param-name">误差限</span>
          <input
            data-testid="tolerance-input"
            type="number"
            min="0"
            value={tolerance}
            onChange={(e) => onTolerance(e.target.value === "" ? "" : Number(e.target.value))}
          />
          <span className="param-hint">每组两侧间隔和之差的上限</span>
        </label>
        <label className="param">
          <span className="param-name">脉冲改动预算</span>
          <input
            data-testid="budget-input"
            type="number"
            min="0"
            value={budget}
            onChange={(e) => onBudget(e.target.value === "" ? "" : Number(e.target.value))}
          />
          <span className="param-hint">可接受的漏检 / 噪声脉冲改动总数</span>
        </label>
      </div>
    </section>
  );
}
