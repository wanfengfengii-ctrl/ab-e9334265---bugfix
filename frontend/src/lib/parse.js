// 输入解析与客户端校验（与后端规则保持一致）

export const LIMITS = {
  bladesMin: 12,
  bladesMax: 160,
  measuredMin: 10,
  measuredMax: 200,
  maxInterval: 1e9,
};

/** 解析逗号 / 空白 / 换行分隔的正整数序列 */
export function parseIntervals(text) {
  const values = [];
  const errors = [];
  String(text)
    .split(/[\s,;，、；]+/)
    .filter((t) => t.length > 0)
    .forEach((token, i) => {
      const v = Number(token);
      if (!Number.isInteger(v) || v <= 0) {
        errors.push(`第 ${i + 1} 项「${token}」不是正整数`);
      } else {
        values.push(v);
      }
    });
  return { values, errors };
}

/** 解析「编号,间隔」逐行文本（也接受空白 / 制表符分隔） */
export function parseBladeRows(text) {
  const blades = [];
  const intervals = [];
  const errors = [];
  String(text)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .forEach((line, idx) => {
      if (!line) return;
      const parts = line.split(/[\s,;\t]+/).filter(Boolean);
      if (parts.length !== 2) {
        errors.push(`第 ${idx + 1} 行格式应为「编号,间隔」：${line}`);
        return;
      }
      const v = Number(parts[1]);
      if (!parts[0]) {
        errors.push(`第 ${idx + 1} 行编号为空`);
      } else if (!Number.isInteger(v) || v <= 0) {
        errors.push(`第 ${idx + 1} 行间隔「${parts[1]}」不是正整数`);
      } else {
        blades.push(parts[0]);
        intervals.push(v);
      }
    });
  return { blades, intervals, errors };
}

/**
 * 归一化 JSON 配置：接受完整对位配置、{blades, intervals}、
 * {intervals:[...]} 或裸数组，返回可填充表单的字段。
 */
export function extractConfig(obj) {
  if (obj == null || typeof obj !== "object") {
    throw new Error("JSON 顶层必须是对象");
  }
  const out = {};
  const ref = obj.reference && typeof obj.reference === "object" ? obj.reference : obj;
  if (Array.isArray(ref.blades) && Array.isArray(ref.intervals)) {
    out.blades = ref.blades.map(String);
    out.refIntervals = ref.intervals.map(Number);
  }
  const meas = obj.measured && typeof obj.measured === "object" ? obj.measured : null;
  if (meas && Array.isArray(meas.intervals)) {
    out.measured = meas.intervals.map(Number);
  } else if (Array.isArray(obj.measured)) {
    out.measured = obj.measured.map(Number);
  }
  if (obj.tolerance !== undefined) out.tolerance = Number(obj.tolerance);
  if (obj.budget !== undefined) out.budget = Number(obj.budget);
  if (!out.blades && !out.measured) {
    throw new Error("未识别到参考叶片环（blades + intervals）或实测间隔（measured.intervals）");
  }
  return out;
}

/** 客户端校验，返回问题列表（空数组表示可提交） */
export function validateConfig({ blades, refIntervals, measured, tolerance, budget }) {
  const issues = [];
  if (blades.length < LIMITS.bladesMin || blades.length > LIMITS.bladesMax) {
    issues.push(`叶片数量须为 ${LIMITS.bladesMin}–${LIMITS.bladesMax}（当前 ${blades.length}）`);
  }
  if (blades.some((b) => !b || !b.trim())) {
    issues.push("存在空白叶片编号");
  }
  const seen = new Set();
  for (const b of blades) {
    if (seen.has(b)) {
      issues.push(`叶片编号重复：${b}`);
      break;
    }
    seen.add(b);
  }
  if (refIntervals.length !== blades.length) {
    issues.push(`参考间隔数量（${refIntervals.length}）须与叶片数量（${blades.length}）一致`);
  }
  if (refIntervals.some((v) => !Number.isInteger(v) || v <= 0)) {
    issues.push("参考间隔必须全部为正整数");
  }
  if (measured.length < LIMITS.measuredMin || measured.length > LIMITS.measuredMax) {
    issues.push(`实测间隔数量须为 ${LIMITS.measuredMin}–${LIMITS.measuredMax}（当前 ${measured.length}）`);
  }
  if (measured.some((v) => !Number.isInteger(v) || v <= 0)) {
    issues.push("实测间隔必须全部为正整数");
  }
  if (!Number.isInteger(tolerance) || tolerance < 0) {
    issues.push("误差限须为非负整数");
  }
  if (!Number.isInteger(budget) || budget < 0) {
    issues.push("改动预算须为非负整数");
  }
  if (issues.length === 0) {
    const s1 = refIntervals.reduce((a, b) => a + b, 0);
    const s2 = measured.reduce((a, b) => a + b, 0);
    if (s1 !== s2) {
      issues.push(`两环总周长必须相等：参考 ${s1} ≠ 实测 ${s2}`);
    }
  }
  return issues;
}
