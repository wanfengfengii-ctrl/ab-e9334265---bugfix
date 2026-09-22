"""请求 / 响应模型与输入校验。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

MIN_BLADES = 12
MAX_BLADES = 160
MIN_MEASURED = 10
MAX_MEASURED = 200
MAX_INTERVAL = 10**9
MAX_TOLERANCE = 10**12
MAX_BUDGET = 10**6


class ReferenceRing(BaseModel):
    """参考叶片环：唯一叶片编号 + 相邻叶片间的正整数间隔（循环解释）。"""

    blades: list[str] = Field(
        ..., description=f"叶片编号列表，{MIN_BLADES}..{MAX_BLADES} 个且唯一"
    )
    intervals: list[int] = Field(
        ..., description="相邻叶片间隔（正整数），与叶片一一对应"
    )

    @field_validator("blades")
    @classmethod
    def _check_blades(cls, value: list[str]) -> list[str]:
        cleaned = [b.strip() for b in value]
        if not (MIN_BLADES <= len(cleaned) <= MAX_BLADES):
            raise ValueError(
                f"叶片数量须为 {MIN_BLADES}..{MAX_BLADES}，当前 {len(cleaned)}"
            )
        for b in cleaned:
            if not b:
                raise ValueError("叶片编号不能为空")
            if len(b) > 40:
                raise ValueError(f"叶片编号过长（>40 字符）：{b!r}")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("叶片编号必须唯一，存在重复编号")
        return cleaned

    @field_validator("intervals")
    @classmethod
    def _check_intervals(cls, value: list[int]) -> list[int]:
        for v in value:
            if v <= 0:
                raise ValueError(f"间隔必须为正整数，当前值 {v}")
            if v > MAX_INTERVAL:
                raise ValueError(f"间隔过大（>{MAX_INTERVAL}）：{v}")
        return value

    @model_validator(mode="after")
    def _check_length_match(self) -> "ReferenceRing":
        if len(self.intervals) != len(self.blades):
            raise ValueError(
                f"间隔数量（{len(self.intervals)}）须与叶片数量（{len(self.blades)}）一致"
            )
        return self


class MeasuredRing(BaseModel):
    """实测脉冲环：正整数间隔序列（循环解释，脉冲匿名按下标引用）。"""

    intervals: list[int] = Field(
        ..., description=f"实测脉冲间隔，{MIN_MEASURED}..{MAX_MEASURED} 个正整数"
    )

    @field_validator("intervals")
    @classmethod
    def _check_intervals(cls, value: list[int]) -> list[int]:
        if not (MIN_MEASURED <= len(value) <= MAX_MEASURED):
            raise ValueError(
                f"实测间隔数量须为 {MIN_MEASURED}..{MAX_MEASURED}，当前 {len(value)}"
            )
        for v in value:
            if v <= 0:
                raise ValueError(f"实测间隔必须为正整数，当前值 {v}")
            if v > MAX_INTERVAL:
                raise ValueError(f"实测间隔过大（>{MAX_INTERVAL}）：{v}")
        return value


class MatchRequest(BaseModel):
    reference: ReferenceRing
    measured: MeasuredRing
    tolerance: int = Field(..., ge=0, le=MAX_TOLERANCE, description="误差限（组内和之差上限）")
    budget: int = Field(..., ge=0, le=MAX_BUDGET, description="脉冲改动预算")

    @model_validator(mode="after")
    def _check_circumference(self) -> "MatchRequest":
        ref_total = sum(self.reference.intervals)
        meas_total = sum(self.measured.intervals)
        if ref_total != meas_total:
            raise ValueError(
                f"两环总周长必须相等：参考环 {ref_total} ≠ 实测环 {meas_total}"
            )
        return self


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------

class GroupOut(BaseModel):
    index: int
    refStart: int
    refCount: int
    refBlades: list[str]
    refSum: int
    measIndices: list[int]
    measSum: int
    absError: int
    modifications: int


class WitnessOut(BaseModel):
    mappingId: str
    direction: str
    offset: int
    groups: list[GroupOut]


class ObjectiveOut(BaseModel):
    modifications: int
    totalAbsError: int
    maxGroupError: int


class BudgetOut(BaseModel):
    limit: int
    used: int
    within: bool


class MatchResponse(BaseModel):
    status: str                     # unique | ambiguous | no_solution
    message: str | None
    objective: ObjectiveOut | None
    budget: BudgetOut
    circumference: int
    optimalMappingCount: int        # 最优规范映射数（精确值；超出 2^53 时 JS 侧请用下一字段）
    optimalMappingCountText: str    # 同一计数的十进制字符串，供前端无精度损失展示
    configurationsExamined: int
    computeMs: int
    witnesses: list[WitnessOut]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
