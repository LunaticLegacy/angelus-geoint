<div align="center">

<img src="src-tauri/icons/icon.png" alt="Angelus icon" width="104" height="104" />

# Angelus GEOINT · 阡陌问旱

### 本地优先的农业干旱证据调查智能体

**自然语言提问 · 遥感/降水证据 · 地图证据联动 · 可追溯调查报告**

[项目简介](#项目简介) · [核心能力](#核心能力) · [架构](#架构) · [数据与证据契约](#数据与证据契约) · [安全边界](#安全边界) · [快速开始](#快速开始) · [测试](#测试与验证) · [文档](#文档)

</div>

![Angelus multi-agent execution graph](docs/assets/angelus-hero.png)

---

## 项目简介

**Angelus GEOINT（阡陌问旱）** 是一个面向农业干旱调查的本地优先智能体工作台：
用户选择区域、时段并发送自然语言问题，系统以 **Angelus Agent 控制平面**编排
调查任务，用 **GEOINT 领域服务**完成空间数据计算，并在 OpenLayers 地图上
呈现带证据的图层与调查报告。

它解决的问题不是"让 Agent 跑起来"，而是让一次干旱调查**可复核**：

```text
选定区域与时段
      │
      ▼
自然语言调查问题
      │
      ▼
数据可用性检查 → 调查计划与授权工具调用
      │
      ▼
数据质量检查 / 对齐 / 空间统计       ← 空间数值由确定性程序计算，LLM 不编造数字
      │
      ▼
地图展示 ⇄ 带证据的调查报告
      │
      ▼
人工复核与导出 · 会话恢复
```

调查输出的每个数字都能回到对应的统计记录与数据来源；事实、推断与缺失被
明确区分，而不是把 LLM 生成的文字当作计算结果。

本仓库是面向 **AI+农林行业应用赛** 的原型作品包（方案见
[`docs/参赛方案.md`](docs/参赛方案.md)）。系统定位为辅助调查与研究；
作物损失评估、灌溉处方与灾害等级需要地面观测与专业验证，不属于首版承诺。

---

## 核心能力

### 调查与证据

- **自然语言调查**：Agent 将问题拆解为调查计划，按需调用工具，结构化汇报；
- **证据关联报告**：结论引用地图图层、数据记录、参数与来源，可逐项追溯；
- **不确定性与缺失呈现**：数据缺口直接显示缺失，不以简单偏差冒充
  SPI/SPEI、干旱预测或灾损评估；
- **会话恢复**：调查过程、结果、参数与来源持久化，重启后继续检查与回放。

### GEOINT 领域服务（`angelus/geoint/`）

- **干旱分析**：同期异常指标统计（NDVI / 降水 / 土壤湿度）、GeoJSON 几何与
  CRS 约定、本地资产与结果物化，以及合成兼容输出；
- **资产目录**：能力式目录与有界公开 HTTP(S) 物化，分析只使用已登记资产；
- **地图文档**：严格会话绑定的 `MapDocument`、图层工厂、栅格显示派生与
  样式（拉伸/分类）、底图与天地图固定主机代理；
- **数据接入**：会话绑定浏览器上传（GeoJSON / GeoTIFF / Shapefile），
  Shapefile 校验完整同名前缀包并经 GDAL/OGR 转换为受管 GeoJSON；
- **Agent 工具**：会话作用域、不暴露宿主路径的 GEOINT Agent 工具提供者，
  允许 Agent 管理会话地图图层与图层样式。

### 工作台（前端）

- **OpenLayers 地图中心**：本地构建，无 Leaflet/CDN 依赖；
- **调查聊天**：持久时间线，消费会话消息投影与 SSE 事件流，Markdown 净化；
- **图层检查器与图层面板**：会话地图文档的一等公民组件；
- **拖拽面板布局**：左/右/底部停靠区、地图边缘分割条，本地持久化；
- **会话作用域请求**：防止过期会话的响应污染控制器或地图图层；
- **桌面文件拖放**：Tauri 壳持有 OS 拖拽路径与字节流，同样走会话作用域导入。

### 桌面应用（Tauri）

Python 后端以 sidecar 打包进桌面壳，最终用户无需预装 Python/虚拟环境；
开发态可用 `ANGELUS_BACKEND_EXECUTABLE` 指向自定义后端。

---

## 架构

```text
┌────────────────────── 用户 ──────────────────────┐
│                                                  │
│       Browser / Tauri  ·  OpenLayers 工作台      │
│  调查聊天 · 地图 · 图层面板 · 拖拽面板 · 设置     │
└────────────────────────┬─────────────────────────┘
                         │
                FastAPI（/api/geoint · /api/sessions
                /api/runs(SSE) · /api/plugins · …）
                         │
┌────────────────────────▼─────────────────────────┐
│              Angelus 控制平面                    │
│                                                  │
│  AngelusCore → SessionHandler → Session          │
│   Session 是执行 / Agent / Swarm 的唯一所有者     │
│  Run Control · 事件账本 · 任务计划 · 插件 / MCP   │
└────────────────────────┬─────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────┐
│            angelus.geoint · GEOINT 领域包        │
│                                                  │
│  catalog · assets · ingestion · processing       │
│  analysis · mapping · agent(tools) · runtime     │
│  （PostGIS 可选，仅用于精确几何求交）             │
└────────────────────────┬─────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────┐
│              LLMFetcher（子模块）                │
│                                                  │
│  Agent Loop · Provider Backends · 工具执行       │
│  上下文/压缩 · 图记忆 · AgentSwarm · TaskBus     │
└────────────────────────┬─────────────────────────┘
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
          LLM API      MCP Tools    Local Tools
```

各层刻意分离，可独立演进：

```text
LLM execution machinery → Agent runtime → Swarm → 控制平面 → 工作台
```

API 层（`angelus/api/`）只是传输适配器：解析输入、调用一个服务、把已知领域错误
映射为 HTTP，不拥有 Session / Agent / 执行 / 凭据。

---

## 数据与证据契约

### 本地指标数据（`data/`）

离线研判只从 `data/` 及其子目录读取已登记文件。当前离线闭环接受
GeoJSON `FeatureCollection`，坐标为 WGS84（EPSG:4326），`properties` 提供
标准化同期异常值：

| 字段 | 说明 |
| --- | --- |
| `ndvi_anomaly`、`rainfall_anomaly`、`soil_moisture_anomaly` | 必填数值，负值表示较同期偏低 |
| `confidence` | 可选，0–1 |
| `observed_at`、`source` | 观测时间与来源 |

登记后系统记录文件 SHA-256；**修改原文件后必须重新登记**，否则结果不可追溯。

### CRS 约定

- 矢量交换、API 与 GeoJSON：WGS84（EPSG:4326）；
- 栅格裁切、重采样、面积与距离计算：WGS 84 / Plate Carrée（EPSG:32662）；
  离散土地利用分类只允许最近邻重采样；
- Web 地图瓦片可能以 EPSG:3857（Web Mercator）渲染，仅为显示，不是分析坐标系。

### 输出溯源

- 风险研判路径只使用已登记本地指标资产，结果标记 `local-asset-indicators`，
  不会把合成数据冒充真实观测；
- 遗留 `/drought/analyze` 兼容路径输出显式标记的 `prototype-synthetic`；
- 精确几何求交需要 PostGIS（`ANGELUS_GEOINT_DATABASE_URL`）；数据库不可达时
  返回服务不可用，绝不把合成输出升级为真实观测结论。

---

## 安全边界

Agent 工作台会执行代码、访问地图资产、调用远端服务并启动本地进程，
因此工具访问被视为安全边界：

- **会话即边界**：`Session` 是执行、Agent、Swarm 与状态的唯一所有者；
  每个会话的状态隔离在 `.angelus-state/sessions/<id>/`；
- **会话级 Shell 沙盒**（进行中）：Agent Shell 通过 Bubblewrap 挂载命名空间
  执行，只把当前 Workspace 挂载为 `/workspace` 可写目录，默认隔离网络、
  PID 与用户命名空间；`bwrap` 不可用时**拒绝执行**，绝不静默降级到宿主 Shell；
- **插件门禁**：显式权限门禁、完整性校验、命名空间隔离与 enable/disable 控制；
- **凭据边界**：运行时快照不含凭据、API Key 受保护、MCP 配置受限、
  浏览器 localStorage 只存 UI 选择，不存凭据；
- **底图代理**：仅固定主机天地图瓦片适配，不做任意 URL 代理。

---

## 快速开始

### 前置条件

- Python 3.12+（3.14 需先 `pip install --upgrade pip setuptools`）
- Git
- 一个可访问的模型服务
- 桌面端开发需要 Node.js（≥18）

### 克隆与安装

```bash
git clone --recurse-submodules https://github.com/LunaticLegacy/angelus-geoint.git
cd angelus-geoint

python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools
python -m pip install --no-build-isolation -e ./llmfetcher
python -m pip install --no-build-isolation -e ".[test]"
```

### 启动浏览器工作台

```bash
angelus web --host 127.0.0.1 --port 8765
```

打开 <http://127.0.0.1:8765>：

1. 在设置中创建 Connector（Provider / Model / API URL / API Key）；
2. 创建会话并选择项目目录；
3. 向调查聊天发送问题，或在导入面板上传 GeoJSON / GeoTIFF / Shapefile。

会话与运行也支持 CLI：

```bash
angelus session list
angelus session create <session_id> <name> <project_path>
```

### 构建前端地图包

GEOINT 工作台由 `frontend/geoint-src/` 经 Vite 构建到 `static/geoint-dist/`：

```bash
npm install
npm run build:geoint
```

### 桌面应用（Tauri）

```bash
npm install
python -m pip install -r requirements-desktop.txt
npm run dev               # 开发运行
npm run build             # 构建安装包（Release 会把 Python 后端打包为 sidecar）
npm run build:backend     # 仅构建后端 sidecar
```

---

## 测试与验证

```bash
# 后端（仓库根目录）
python -m unittest discover -s tests

# GEOINT 前端单元测试
npm run test:geoint

# 基础语法检查
node --check frontend/static/app.js

# 桌面壳
cargo check --manifest-path src-tauri/Cargo.toml
```

测试构造隔离的临时状态根，不需要真实 API 凭据，也不会改动仓库的
`.angelus-state/`。后端覆盖：执行与停止控制、会话控制台、插件管理、
GEOINT 服务/运行时/导入/Shapefile/栅格呈现/样式/目录/本地与远端资产/底图等；
前端覆盖：API 适配、会话请求作用域、地图、栅格渲染样式、图层面板、
Trace 视图、调查事件投影等。

---

## 项目结构

```text
angelus/
    Angelus 控制平面：core、modules（session / execution / tool 等）、api
angelus/geoint/
    GEOINT 领域包：analysis / assets / catalog / imports / ingestion /
    landuse / mapping / processing / agent(tools) / runtime
frontend/
    geoint-src/        OpenLayers 工作台模块源码（Vite 构建）
    static/geoint-dist/ 构建产物；templates/ SPA 壳
llmfetcher/
    Agent 运行时子模块：Agent Loop、Swarm、TaskBus、工具、图记忆
src-tauri/
    桌面壳：sidecar 生命周期、原生文件拖放、打包
plugins/
    插件系统与示例（demo-hello、example-tool、gzctf、pofp-ctf 等）
data/
    已登记本地指标数据与契约说明（data/README.md）
docs/
    架构、安全、插件契约、GEOINT 模块化设计与参赛方案
.modular/
    模块化开发各阶段工件（边界/契约/依赖图/验证/实现计划）
literature/
    干旱分析研究资料
tests/
    回归与集成测试
scripts/
    构建与运行时入口
.github/workflows/
    CI 与桌面 Release 构建
```

可检索仓库地图：

[INDEX.md](INDEX.md) · [angelus/INDEX.md](angelus/INDEX.md) ·
[angelus/geoint/INDEX.md](angelus/geoint/INDEX.md) ·
[angelus/api/INDEX.md](angelus/api/INDEX.md) ·
[frontend/INDEX.md](frontend/INDEX.md) · [tests/INDEX.md](tests/INDEX.md) ·
[llmfetcher/INDEX.md](llmfetcher/INDEX.md)

---

## 文档

| 主题 | 文档 |
| --- | --- |
| GEOINT 模块化架构与数据契约 | [docs/geoint-modular-architecture.md](docs/geoint-modular-architecture.md) |
| 参赛方案与交付门槛 | [docs/参赛方案.md](docs/参赛方案.md) |
| 代码语义参考 | [docs/semantic-map.md](docs/semantic-map.md) |
| 当前架构（Mermaid） | [docs/current-code-architecture-mermaid.md](docs/current-code-architecture-mermaid.md) |
| 安全边界 | [docs/security.md](docs/security.md) |
| 插件开发 / Plugin API | [docs/plugin-guide.md](docs/plugin-guide.md) · [docs/plugin-api.md](docs/plugin-api.md) |
| 设计决策 | [docs/decisions.md](docs/decisions.md) |
| 图上下文与归档检索 | [docs/graph_context_design.md](docs/graph_context_design.md) |
| 层级知识检索论文草稿 | [docs/mnavrag-arxiv-draft.md](docs/mnavrag-arxiv-draft.md) |
| 发布说明 | [CHANGELOG.md](CHANGELOG.md) |

---

## 开发状态

原型处于活跃开发阶段（当前分支 `private/geoint-drought`）。已完成：

- GEOINT 领域包与模块化架构（`.modular/` 各阶段工件与本仓库
  `architecture.yaml` 对齐）；
- 会话作用域导入（GeoJSON / GeoTIFF / Shapefile）与地图文档、栅格显示语义；
- 调查聊天、图层面板、拖拽面板布局与 SSE 事件流；
- 桌面壳原生文件拖放导入。

进行中：**会话级 Shell 沙盒**（`angelus/modules/tool_module/session_sandbox.py`
与 `runtime_provider.py` 尚在工作树内未提交）。

按 [`docs/参赛方案.md`](docs/参赛方案.md)，交付前仍需逐项证明：固定案例数据
清单与实际覆盖、真实县域区域统计与独立复核、与统计一致的图层、逐项可追溯的
证据报告、浏览器实测交互（选择项目/运行/看结果/恢复会话）、稳定性（刷新/
切换会话/断网/停止/无数据反馈）与打包可交付物（安装说明、固定依赖、演示数据、
示例报告、演示视频）。当前不宣称任何未经测量的节水、增产或准确率收益。

---

# 许可证

本仓库使用 **AGPL-3.0-or-later**，并保留独立商业授权路径
（[LICENSING.md](LICENSING.md) · [commercial-licensing.md](commercial-licensing.md)）。
LLMFetcher 是独立仓库，遵循其自身的版权与许可证声明。