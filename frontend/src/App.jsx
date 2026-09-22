import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { postMatch } from "./api";
import { extractConfig, validateConfig } from "./lib/parse";
import ReferenceEditor from "./components/ReferenceEditor";
import MeasuredEditor from "./components/MeasuredEditor";
import ParamsPanel from "./components/ParamsPanel";
import ResultPanel from "./components/ResultPanel";

const PRESETS = [
  { key: "unique", label: "示例 · 唯一解" },
  { key: "realistic", label: "示例 · 现场噪声" },
  { key: "ambiguous", label: "示例 · 歧义" },
  { key: "no-solution", label: "示例 · 无解" },
];

export default function App() {
  const [blades, setBlades] = useState([]);
  const [refIntervals, setRefIntervals] = useState([]);
  const [measured, setMeasured] = useState([]);
  const [tolerance, setTolerance] = useState(2);
  const [budget, setBudget] = useState(4);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [preset, setPreset] = useState("");
  const [configVersion, setConfigVersion] = useState(0);
  const importRef = useRef(null);

  const issues = useMemo(
    () => validateConfig({ blades, refIntervals, measured, tolerance, budget }),
    [blades, refIntervals, measured, tolerance, budget]
  );

  const applyConfig = useCallback((cfg) => {
    if (cfg.blades && cfg.refIntervals) {
      setBlades(cfg.blades);
      setRefIntervals(cfg.refIntervals);
    }
    if (cfg.measured) setMeasured(cfg.measured);
    if (Number.isInteger(cfg.tolerance)) setTolerance(cfg.tolerance);
    if (Number.isInteger(cfg.budget)) setBudget(cfg.budget);
    setResult(null);
    setError(null);
    setConfigVersion((v) => v + 1);
  }, []);

  const loadPreset = useCallback(
    async (key) => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`/examples/${key}.json`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        applyConfig({ ...extractConfig(await res.json()) });
        setPreset(key);
      } catch (e) {
        setError(`示例加载失败：${e.message}`);
      } finally {
        setLoading(false);
      }
    },
    [applyConfig]
  );

  // 首次进入自动载入唯一解示例
  useEffect(() => {
    loadPreset("unique");
  }, [loadPreset]);

  const importConfigFile = (file) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        applyConfig(extractConfig(JSON.parse(String(reader.result || ""))));
        setPreset("");
      } catch (e) {
        setError(`配置导入失败：${e.message}`);
      }
    };
    reader.readAsText(file);
  };

  const exportConfig = () => {
    const payload = {
      reference: { blades, intervals: refIntervals },
      measured: { intervals: measured },
      tolerance,
      budget,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "blade-align-config.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleAlign = async () => {
    setError(null);
    if (issues.length) {
      setResult(null);
      setError(`请先修正输入：${issues[0]}`);
      return;
    }
    setLoading(true);
    try {
      const data = await postMatch({
        reference: { blades, intervals: refIntervals },
        measured: { intervals: measured },
        tolerance,
        budget,
      });
      setResult(data);
    } catch (e) {
      setResult(null);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>叶尖脉冲对位复核台</h1>
          <p className="subtitle">燃气轮机检修 · 参考叶片环 × 实测脉冲环的全局最优对位</p>
        </div>
        <div className="header-actions">
          <button className="btn" onClick={() => importRef.current?.click()}>
            导入配置
          </button>
          <button className="btn" data-testid="export-config" onClick={exportConfig}>
            导出配置
          </button>
          <input
            ref={importRef}
            type="file"
            accept=".json"
            hidden
            onChange={(e) => e.target.files?.[0] && importConfigFile(e.target.files[0])}
          />
        </div>
      </header>

      <main className="layout">
        <span data-testid="config-version" data-version={configVersion} hidden />
        <div className="left-col">
          <div className="preset-bar">
            {PRESETS.map((p) => (
              <button
                key={p.key}
                data-testid={`preset-${p.key}`}
                className={`btn preset ${preset === p.key ? "active" : ""}`}
                onClick={() => loadPreset(p.key)}
              >
                {p.label}
              </button>
            ))}
          </div>

          <ReferenceEditor
            blades={blades}
            refIntervals={refIntervals}
            onChange={({ blades: b, refIntervals: ri }) => {
              setBlades(b);
              setRefIntervals(ri);
            }}
          />
          <MeasuredEditor measured={measured} onChange={setMeasured} />
          <ParamsPanel
            tolerance={tolerance}
            budget={budget}
            onTolerance={setTolerance}
            onBudget={setBudget}
          />

          {issues.length > 0 && (
            <ul className="error-list" data-testid="client-issues">
              {issues.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          )}

          <button
            className="btn primary align-btn"
            data-testid="align-button"
            disabled={loading}
            onClick={handleAlign}
          >
            {loading ? "对位中…" : "发起对位"}
          </button>
        </div>

        <div className="right-col">
          <ResultPanel
            result={result}
            error={error}
            loading={loading}
            blades={blades}
            refIntervals={refIntervals}
            measured={measured}
          />
        </div>
      </main>

      <footer className="app-footer">
        对位目标：依次最小化 改动数 → 总绝对误差 → 最大组误差 ｜ 每组任一侧至多 3 个间隔 ｜
        完整考察实测环两个方向与全部起点
      </footer>
    </div>
  );
}
