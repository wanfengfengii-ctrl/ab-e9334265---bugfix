# 叶尖脉冲对位复核台

燃气轮机检修场景中，叶尖传感器一圈脉冲可能**漏检真实叶片**或**混入反光噪声**，
逐点就近对齐会在重复间距处整体错位。本系统把参考叶片环与实测脉冲环做**全局最优
对位**：工程师在浏览器中导入或编辑参考叶片环、实测间隔、误差限与脉冲改动预算，
通过真实 API 发起对位并查看环形映射；后端完整考察实测环的两个方向与全部起点，
依次最小化 **改动数 → 总绝对误差 → 最大组误差**，并以规范映射判定 **唯一 / 歧义 /
无解**，歧义时返回两份不同最优见证供前端逐组高亮对比。

## 快速开始

```bash
cp .env.example .env          # 可选：修改宿主机端口
docker compose up --build     # 启动前端 + 后端（含健康检查）
# 浏览器打开 http://localhost:8080
```

运行验收（驱动无头浏览器完成端到端联调复核，截图输出到 `./artifacts`）：

```bash
docker compose --profile verify up --build --exit-code-from verify
# 或：docker compose --profile verify run --rm verify
```

`verify` 服务全部检查通过时以退出码 0 结束。

## 端口配置

宿主机端口通过环境变量配置（默认值见 `.env.example`）：

| 变量       | 默认 | 说明                       |
| ---------- | ---- | -------------------------- |
| `WEB_PORT` | 8080 | 前端 Web（浏览器入口）     |
| `API_PORT` | 8000 | 后端 API（可选暴露调试）   |

## 问题模型

- **参考叶片环**：12–160 个唯一叶片编号 + 相邻正整数间隔，按循环解释；
- **实测脉冲环**：10–200 个正整数间隔，按循环解释，脉冲匿名以 `#序号` 引用；
- 两环**总周长必须相等**（否则 422）；
- **一次对位**：两环分别切成数量相同的连续非空组，每组任一侧至多 3 个间隔，
  组内两侧间隔和之差不超过误差限；
- **改动数**：各组两侧超出一个间隔的数量之和（= n + m − 2k，k 为组数），
  即解释数据所需的漏检 / 噪声脉冲总数，须不超过改动预算；
- **目标**：按字典序依次最小化 改动数、总绝对误差、最大组误差。

## 求解算法

固定参考环起点（叶片编号是绝对坐标），枚举实测环 **2 个方向 × 全部 m 个起点**
共 2m 个配置。对每个配置做分组动态规划：`dp[i][j]` 为参考环前 i 个间隔与实测环
前 j 个间隔对齐的最优字典序代价，转移枚举最后一组两侧跨度 (a, b) ∈ {1,2,3}²。
所有配置的 DP 以 numpy 向量化批量推进（按参考前缀逐行滚动），并同步维护最优
路径的**精确计数**（int64 快速推进并在高位阈值处饱和探测，一旦触及即以
Python 任意精度整数重算，因此计数可超出 int64 / JS 安全整数而保持精确）。

一个对位映射由 **(方向, 起点, 各组切分)** 完全确定（其规范形式），最优路径计数
即最优规范映射数：

- 计数 = 0 → `no_solution`；
- 计数 = 1 → `unique`，返回该见证；
- 计数 ≥ 2 → `ambiguous`，返回两份规范形式不同的最优见证（优先不同配置，
  同一配置内则在最后一个存在备选最优转移的单元处分叉），供前端逐组高亮差异。

复杂度：O(n·m·方向起点数) ≈ 160×200×400 上限规模，向量化后约 1–3 s；
常规规模（数十叶片）为毫秒级。

## API

### `GET /api/health`

健康检查，返回 `{"status": "ok", ...}`。

### `POST /api/match`

请求体：

```json
{
  "reference": { "blades": ["B01", "..."], "intervals": [50, 52, 48] },
  "measured": { "intervals": [50, 100, 51] },
  "tolerance": 2,
  "budget": 4
}
```

响应（节选）：

```json
{
  "status": "unique | ambiguous | no_solution",
  "objective": { "modifications": 1, "totalAbsError": 0, "maxGroupError": 0 },
  "budget": { "limit": 4, "used": 1, "within": true },
  "circumference": 600,
  "optimalMappingCount": 1,
  "optimalMappingCountText": "1",
  "configurationsExamined": 22,
  "computeMs": 3,
  "witnesses": [
    {
      "mappingId": "2ae46920118c",
      "direction": "forward",
      "offset": 0,
      "groups": [
        {
          "index": 1, "refStart": 1, "refCount": 2, "refBlades": ["B02", "B03"],
          "refSum": 100, "measIndices": [1], "measSum": 100,
          "absError": 0, "modifications": 1
        }
      ]
    }
  ]
}
```

- `witnesses`：唯一解 1 份、歧义 2 份、无解 0 份；
- `optimalMappingCount`：最优规范映射数的精确值（JSON 数字）；
  `optimalMappingCountText` 为同一计数的十进制字符串——计数可能超出
  JavaScript 安全整数范围，前端一律以该字符串精确展示；
- `direction` / `offset`：实测环的行进方向与对齐起点（原始下标）；
- `budget.within`：最优改动数是否在预算内（超预算时前端给出警示，不影响求解）；
- 输入非法（编号重复、数量越界、非正整数、周长不等……）返回 422 与中文原因。

完整交互式文档：启动后访问 `http://localhost:8000/docs`。

## 本地开发

```bash
# 后端（Python 3.11+）
cd backend
pip install -r requirements-dev.txt
uvicorn app.main:app --reload          # http://localhost:8000
pytest                                 # 83 项测试（含暴力枚举对照）

# 前端（Node 20+）
cd frontend
npm ci
npm run dev                            # http://localhost:5173（代理 /api → 8000）
npm test                               # vitest
npm run build                          # 产物 dist/
```

## 项目结构

```
├── docker-compose.yml      # backend / frontend / verify 编排与健康检查
├── backend/                # FastAPI + numpy 求解器
│   ├── app/matcher.py      #   分组 DP（向量化）+ 规范映射判定 + 见证重构
│   ├── app/main.py         #   路由：/api/health、/api/match
│   ├── app/schemas.py      #   请求校验与响应模型
│   └── tests/              #   手工案例 + 暴力枚举随机对照 + API 测试
├── frontend/               # React + Vite，nginx 托管并代理 /api
│   ├── src/components/     #   编辑器、环形映射图、组明细表、结果面板
│   └── public/examples/    #   内置示例（唯一 / 歧义 / 无解 / 现场噪声）
└── verify/                 # 验收服务：Playwright 驱动浏览器做端到端复核
```

## 验收说明

`verify` 服务依次执行：

1. 等待前端 `/healthz` 与后端 `/api/health` 健康；
2. **API 级**：四类示例的状态、目标值、见证数量、预算标记、周长不等 422；
3. **浏览器级**：自动载入示例 → 发起对位 → 校验状态横幅、统计指标、环形图
   组弧数量、组明细表、组联动高亮、双见证切换与差异高亮、超预算警示、
   客户端校验拦截；
4. 截图保存至 `./artifacts`，全部通过退出码 0。
