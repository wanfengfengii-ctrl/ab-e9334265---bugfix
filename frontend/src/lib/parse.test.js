import { describe, expect, it } from "vitest";

import {
  extractConfig,
  parseBladeRows,
  parseIntervals,
  validateConfig,
} from "./parse";
import {
  diffGroupKeys,
  groupKey,
  measArcFractions,
  prefixSums,
} from "./geometry";

describe("parseIntervals", () => {
  it("解析多种分隔符", () => {
    const { values, errors } = parseIntervals("50, 52\n48；51，49、53 47");
    expect(errors).toEqual([]);
    expect(values).toEqual([50, 52, 48, 51, 49, 53, 47]);
  });

  it("拒绝非正整数", () => {
    const { values, errors } = parseIntervals("50, -3, abc, 0, 2.5");
    expect(values).toEqual([50]);
    expect(errors).toHaveLength(4);
  });
});

describe("parseBladeRows", () => {
  it("解析编号与间隔", () => {
    const { blades, intervals, errors } = parseBladeRows("B01,50\nB02 52\nB03\t48");
    expect(errors).toEqual([]);
    expect(blades).toEqual(["B01", "B02", "B03"]);
    expect(intervals).toEqual([50, 52, 48]);
  });

  it("报告坏行", () => {
    const { errors } = parseBladeRows("B01,50\n坏行\nB03,x");
    expect(errors).toHaveLength(2);
  });
});

describe("extractConfig", () => {
  it("接受完整配置", () => {
    const cfg = extractConfig({
      reference: { blades: ["B01"], intervals: [50] },
      measured: { intervals: [50] },
      tolerance: 2,
      budget: 4,
    });
    expect(cfg.blades).toEqual(["B01"]);
    expect(cfg.refIntervals).toEqual([50]);
    expect(cfg.measured).toEqual([50]);
    expect(cfg.tolerance).toBe(2);
    expect(cfg.budget).toBe(4);
  });

  it("拒绝无法识别的 JSON", () => {
    expect(() => extractConfig({ hello: 1 })).toThrow();
  });
});

describe("validateConfig", () => {
  const base = {
    blades: Array.from({ length: 12 }, (_, i) => `B${i + 1}`),
    refIntervals: Array(12).fill(50),
    measured: Array(12).fill(50),
    tolerance: 2,
    budget: 4,
  };

  it("合法配置无问题", () => {
    expect(validateConfig(base)).toEqual([]);
  });

  it("检出重复编号", () => {
    const issues = validateConfig({ ...base, blades: base.blades.map((_, i) => (i ? "X" : "X")) });
    expect(issues.some((s) => s.includes("重复"))).toBe(true);
  });

  it("检出周长不等", () => {
    const issues = validateConfig({ ...base, measured: Array(12).fill(51) });
    expect(issues.some((s) => s.includes("周长"))).toBe(true);
  });

  it("检出数量越界", () => {
    expect(validateConfig({ ...base, measured: [1, 2, 3] }).length).toBeGreaterThan(0);
  });
});

describe("geometry", () => {
  it("prefixSums", () => {
    expect(prefixSums([2, 3, 5])).toEqual([0, 2, 5, 10]);
  });

  it("measArcFractions 处理绕环组", () => {
    const cum = prefixSums([10, 10, 10, 10, 10]); // 周长 50
    const { start, end } = measArcFractions([4, 0], cum);
    expect(start).toBeCloseTo(0.8);
    expect(end).toBeCloseTo(1.2);
  });

  it("diffGroupKeys 找出差异组", () => {
    const wA = { groups: [{ refStart: 0, refCount: 1, measIndices: [0] }, { refStart: 1, refCount: 2, measIndices: [1] }] };
    const wB = { groups: [{ refStart: 0, refCount: 1, measIndices: [0] }, { refStart: 1, refCount: 1, measIndices: [1, 2] }] };
    const { onlyA, onlyB } = diffGroupKeys(wA, wB);
    expect(onlyA.size).toBe(1);
    expect(onlyB.size).toBe(1);
    expect([...onlyA][0]).toBe(groupKey(wA.groups[1]));
  });
});
