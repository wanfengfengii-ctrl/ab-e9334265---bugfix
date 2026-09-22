import { useRef, useState } from "react";
import { extractConfig, parseBladeRows, LIMITS } from "../lib/parse";

/**
 * 参考叶片环编辑器：逐行编辑 + 批量导入（JSON / CSV / 文件）
 */
export default function ReferenceEditor({ blades, refIntervals, onChange }) {
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkText, setBulkText] = useState("");
  const [bulkErrors, setBulkErrors] = useState([]);
  const fileRef = useRef(null);

  const sum = refIntervals.reduce((a, b) => a + (Number.isInteger(b) ? b : 0), 0);

  const updateBlade = (i, value) => {
    const next = blades.slice();
    next[i] = value;
    onChange({ blades: next, refIntervals });
  };

  const updateInterval = (i, value) => {
    const next = refIntervals.slice();
    next[i] = value === "" ? "" : Number(value);
    onChange({ blades, refIntervals: next });
  };

  const addRow = () => {
    const next = blades.slice();
    let k = next.length + 1;
    while (next.includes(`B${String(k).padStart(2, "0")}`)) k += 1;
    next.push(`B${String(k).padStart(2, "0")}`);
    onChange({ blades: next, refIntervals: refIntervals.concat([50]) });
  };

  const removeRow = (i) => {
    onChange({
      blades: blades.filter((_, t) => t !== i),
      refIntervals: refIntervals.filter((_, t) => t !== i),
    });
  };

  const applyParsed = (nb, ni) => {
    const errs = [];
    if (nb.length !== ni.length) errs.push("编号与间隔数量不一致");
    if (nb.length < LIMITS.bladesMin || nb.length > LIMITS.bladesMax) {
      errs.push(`叶片数量须为 ${LIMITS.bladesMin}–${LIMITS.bladesMax}（当前 ${nb.length}）`);
    }
    const dup = nb.find((b, i) => nb.indexOf(b) !== i);
    if (dup) errs.push(`叶片编号重复：${dup}`);
    if (errs.length) {
      setBulkErrors(errs);
      return;
    }
    onChange({ blades: nb, refIntervals: ni });
    setBulkErrors([]);
    setBulkOpen(false);
    setBulkText("");
  };

  const applyBulkText = () => {
    const text = bulkText.trim();
    if (!text) {
      setBulkErrors(["请先粘贴内容"]);
      return;
    }
    if (text.startsWith("{")) {
      try {
        const cfg = extractConfig(JSON.parse(text));
        if (!cfg.blades || !cfg.refIntervals) {
          setBulkErrors(["JSON 中未找到 reference.blades / reference.intervals"]);
          return;
        }
        applyParsed(cfg.blades, cfg.refIntervals);
      } catch (e) {
        setBulkErrors([`JSON 解析失败：${e.message}`]);
      }
      return;
    }
    const { blades: nb, intervals: ni, errors } = parseBladeRows(text);
    if (errors.length) {
      setBulkErrors(errors.slice(0, 6));
      return;
    }
    applyParsed(nb, ni);
  };

  const importFile = (file) => {
    const reader = new FileReader();
    reader.onload = () => {
      setBulkText(String(reader.result || ""));
      setBulkOpen(true);
    };
    reader.readAsText(file);
  };

  return (
    <section className="editor" data-testid="reference-editor">
      <div className="editor-head">
        <h2>参考叶片环</h2>
        <div className="badges">
          <span className="badge" data-testid="ref-count">
            {blades.length} 叶片
          </span>
          <span className="badge" data-testid="ref-sum">
            周长 {sum}
          </span>
        </div>
      </div>
      <p className="hint">
        {LIMITS.bladesMin}–{LIMITS.bladesMax} 个唯一叶片编号，间隔为正整数，按循环解释
      </p>

      <div className="table-wrap">
        <table className="edit-table">
          <thead>
            <tr>
              <th>#</th>
              <th>叶片编号</th>
              <th>间隔</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {blades.map((b, i) => (
              <tr key={i}>
                <td className="muted">{i + 1}</td>
                <td>
                  <input
                    className="cell-input"
                    data-testid={`blade-id-${i}`}
                    value={b}
                    onChange={(e) => updateBlade(i, e.target.value)}
                  />
                </td>
                <td>
                  <input
                    className="cell-input num"
                    data-testid={`blade-interval-${i}`}
                    type="number"
                    min="1"
                    value={refIntervals[i] ?? ""}
                    onChange={(e) => updateInterval(i, e.target.value)}
                  />
                </td>
                <td>
                  <button
                    className="icon-btn"
                    title="删除该叶片"
                    onClick={() => removeRow(i)}
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="btn-row">
        <button className="btn" onClick={addRow}>
          + 添加叶片
        </button>
        <button className="btn" onClick={() => setBulkOpen((v) => !v)}>
          批量导入
        </button>
        <button className="btn" onClick={() => fileRef.current?.click()}>
          从文件导入
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".json,.csv,.txt"
          hidden
          onChange={(e) => e.target.files?.[0] && importFile(e.target.files[0])}
        />
      </div>

      {bulkOpen && (
        <div className="bulk-box">
          <textarea
            data-testid="ref-bulk-input"
            rows={6}
            placeholder={'每行一条：B01,50\n或粘贴 JSON：{"blades":[...],"intervals":[...]}'}
            value={bulkText}
            onChange={(e) => setBulkText(e.target.value)}
          />
          <div className="btn-row">
            <button className="btn primary" data-testid="ref-bulk-apply" onClick={applyBulkText}>
              解析并替换
            </button>
          </div>
          {bulkErrors.length > 0 && (
            <ul className="error-list">
              {bulkErrors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
