"""FastAPI 应用入口。"""

from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .matcher import SolveResult, solve
from .schemas import (
    BudgetOut,
    GroupOut,
    HealthResponse,
    MatchRequest,
    MatchResponse,
    ObjectiveOut,
    WitnessOut,
)

VERSION = "1.0.0"

app = FastAPI(
    title="叶尖脉冲对位复核 API",
    version=VERSION,
    description="燃气轮机叶尖传感器脉冲序列与参考叶片环的全局最优对位复核",
)

# 前端经 nginx 同源代理访问；此处放开 CORS 便于本地联调
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="blade-align-backend", version=VERSION)


def _to_response(req: MatchRequest, result: SolveResult, compute_ms: int) -> MatchResponse:
    blades = req.reference.blades
    witnesses: list[WitnessOut] = []
    for w in result.witnesses:
        groups = [
            GroupOut(
                index=g.index,
                refStart=g.ref_start,
                refCount=g.ref_count,
                refBlades=blades[g.ref_start : g.ref_start + g.ref_count],
                refSum=g.ref_sum,
                measIndices=list(g.meas_indices),
                measSum=g.meas_sum,
                absError=g.abs_error,
                modifications=g.modifications,
            )
            for g in w.groups
        ]
        witnesses.append(
            WitnessOut(
                mappingId=w.mapping_id(),
                direction=w.direction,
                offset=w.offset,
                groups=groups,
            )
        )

    objective = None
    if result.objective is not None:
        objective = ObjectiveOut(
            modifications=result.objective.modifications,
            totalAbsError=result.objective.total_abs_error,
            maxGroupError=result.objective.max_group_error,
        )

    used = objective.modifications if objective is not None else 0
    budget = BudgetOut(limit=req.budget, used=used, within=used <= req.budget)

    return MatchResponse(
        status=result.status,
        message=result.message,
        objective=objective,
        budget=budget,
        circumference=sum(req.reference.intervals),
        optimalMappingCount=result.optimal_count,
        optimalMappingCountText=str(result.optimal_count),
        configurationsExamined=result.configurations,
        computeMs=compute_ms,
        witnesses=witnesses,
    )


@app.post("/api/match", response_model=MatchResponse)
def match(req: MatchRequest) -> MatchResponse:
    """发起对位：穷举实测环两个方向与全部起点，返回最优规范映射。"""
    started = time.perf_counter()
    result = solve(
        list(req.reference.intervals),
        list(req.measured.intervals),
        req.tolerance,
    )
    compute_ms = round((time.perf_counter() - started) * 1000)
    return _to_response(req, result, compute_ms)
