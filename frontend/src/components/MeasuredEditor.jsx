import { useMemo, useRef, useState } from "react";
import { extractConfig, parseIntervals, LIMITS } from "../lib/parse";

/**
 * 实测脉冲间隔编辑器：文本批量编辑 + 文件导入
 */
export default function MeasuredEditor({ measured, onChange }) {
  const [text, setText] = useState(() => measured.join(", "));
  const [errors, setErrors] = useState([]);
  const fileRef = useRef(null);

  // 外部（示例 / 配置导入）替换实测序列时同步文本框；
  // 若文本框当前内容解析结果与外部一致（即变更来自本框输入），不回写以免打断输入
  const externalKey = useMemo(() => measured.join(","), [measured]);
  const [shownKey, setShownKey] = useState(externalKey);
  if (externalKey !== shownKey) {
    setShownKey(externalKey);
    const parsed = parseIntervals(text);
    if (parsed.errors.length > 0 || parsed.values.join(",") !== externalKey) {
      setText(measured.join(", "));
      setErrors([]);
    }
  }

  const sum = measured.reduce((a, b) => a + b, 0);

  const applyText = (value) => {
    setText(value);
    const { values, errors: errs } = parseIntervals(value);
    if (errs.length) {
      setErrors(errs.slice(0, 5));
      return;
    }
    setErrors([]);
    onChange(values);
  };

  const importFile = (file) => {
    const reader = new FileReader();
    reader.onload = () => {
      const raw = String(reader.result || "").trim();
      let content = raw;
      if (raw.startsWith("{") || raw.startsWith("[")) {
        try {
          const obj = JSON.parse(raw);
          const cfg = Array.isArray(obj) ? { measured: obj.map(Number) } : extractConfig(obj);
          if (!cfg.measured) throw new Error("未找到 measured.intervals");
          content = cfg.measured.join(", ");
        } catch (e) {
          setErrors([`JSON 解析失败：${e.message}`]);
          return;
        }
      }
      applyText(content);
    };
    reader.readAsText(file);
  };

  return (
    <section className="editor" data-testid="measured-editor">
      <div className="editor-head">
        <h2>实测脉冲间隔</h2>
        <div className="badges">
          <span className="badge" data-testid="meas-count">
            {measured.length} 脉冲
          </span>
          <span className="badge" data-testid="meas-sum">
            周长 {sum}
          </span>
        </div>
      </div>
      <p className="hint">
        {LIMITS.measuredMin}–{LIMITS.measuredMax} 个正整数，按记录顺序循环解释；脉冲匿名，以 #序号 引用
      </p>
      <textarea
        className="meas-input"
        data-testid="meas-input"
        rows={5}
        value={text}
        onChange={(e) => applyText(e.target.value)}
        placeholder="以逗号 / 空格 / 换行分隔的正整数序列"
      />
      {errors.length > 0 && (
        <ul className="error-list">
          {errors.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
      <div className="btn-row">
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
    </section>
  );
}
