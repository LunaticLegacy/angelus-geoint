<div align="center">
  <img src="src-tauri/icons/icon.svg" alt="Angelus GEOINT logo" width="112" />

  # Angelus GEOINT

  ### 面向农业干旱胁迫的多源地理情报分析智能体

  自然语言调查 · 多源地理数据 · 确定性空间计算 · 地图与证据追溯

  [快速开始](#快速开始) · [核心能力](#核心能力) · [系统架构](#系统架构) · [数据与边界](#数据与边界) · [开发与测试](#开发与测试)
</div>

---

## 项目简介

Angelus GEOINT 是一个面向县域农业干旱相关调查的本地优先工作台。用户围绕研究区域、时间范围和具体问题建立会话，导入遥感、气象、行政区边界等数据，由智能体组织可执行的地理工具，再通过地图、执行记录和证据条目查看结果依据。

它不是“让大模型看图后直接给结论”的系统。大语言模型承担问题理解、任务组织和结果说明；裁剪、统计及数据处理应由确定性程序执行。系统会把输入资产、处理过程与结果关联，帮助使用者核查一条判断来自什么数据、经过哪些步骤，并在数据不足时保留不确定性。

项目面向农业科研、遥感教学和基层辅助研判。它不替代农艺专家判断，也不在没有地面观测和充分验证的前提下宣称作物受损、减产或给出灌溉处方。

## 核心能力

- **调查会话**：以会话隔离工作空间、数据资产、运行配置、上下文与执行轨迹；支持恢复历史调查和继续补充要求。
- **多源数据接入**：支持 GeoJSON、GeoTIFF/COG 与 Shapefile。Shapefile 按同名 `.shp`、`.shx`、`.dbf` 文件集合处理，`.prj`、`.cpg` 可选。
- **地图与图层管理**：图层可分组、排序、拖拽调整、显示/隐藏、调整透明度、重命名、移除与缩放定位；地图呈现状态保存到会话。
- **栅格显示**：支持连续值拉伸、多波段组合、单波段分类色盘、类别别名及 NoData/背景值处理。显示设置不修改原始数据。
- **确定性地理处理**：提供会话绑定资产的空间处理与统计能力，输入、参数和输出可作为调查记录保留。
- **智能体工具调用**：Angelus 负责会话、工具权限、执行追踪与上下文；GEOINT 提供不暴露宿主路径的地理资产、处理、地图呈现与证据工具。
- **证据与知识支撑**：调查判断可关联来源资产、处理结果及知识条目，帮助区分原始事实、程序结果、模型解释与信息缺失。
- **浏览器与桌面路径**：浏览器上传通过会话 API 管理；Tauri 桌面壳可使用原生文件选择与拖放，仍走相同的受控导入链路。

## 系统架构

```text
┌──────────────────────────── 用户工作台 ────────────────────────────┐
│  Browser / Tauri · OpenLayers 地图 · 图层面板 · 调查 · 证据 · 设置  │
└──────────────────────────────────┬────────────────────────────────┘
                                   │
                            FastAPI / SSE
                                   │
┌──────────────────────────────────▼────────────────────────────────┐
│ Angelus 控制平面                                                     │
│ Session · Connector · Tool permission · Execution · Context         │
└───────────────────────┬──────────────────────────┬────────────────┘
                        │                          │
              ┌─────────▼────────┐       ┌─────────▼────────┐
              │ GEOINT 领域服务   │       │ LLMFetcher        │
              │ assets · imports │       │ Agent loop        │
              │ mapping · tools  │       │ model providers   │
              │ processing       │       │ tool execution    │
              └─────────┬────────┘       └──────────────────┘
                        │
          GeoJSON · GeoTIFF/COG · Shapefile · 气象/遥感数据
```

### 设计原则

1. **计算与解释分离**：LLM 不替代数值计算；处理结果必须来自实际工具输出。
2. **会话是数据边界**：资产和地图图层属于会话，避免跨调查混用数据。
3. **证据优先**：结论应关联数据来源、参数、处理输出和适用条件。
4. **显示不等于分析**：Web Mercator 与色彩拉伸是显示选择，不应被误认为分析坐标系或新的科学指标。

## 数据与边界

### 支持的数据

| 类型 | 用途 | 注意事项 |
| --- | --- | --- |
| GeoJSON | 边界、河流、行政区、矢量分析结果 | 推荐包含 CRS 信息；交换格式通常使用 EPSG:4326。 |
| Shapefile | 传统矢量数据 | 核心成员为 `.shp`、`.shx`、`.dbf`；导入后转换为受管 GeoJSON。 |
| GeoTIFF / COG | 遥感指标、分类图、气象栅格 | 应检查坐标参考、NoData、波段、数值范围与时间口径。 |
| CSV / NPY / NPZ | 统计表和分析中间成果 | 可用于脚本分析或成果附件，不能直接作为地图图层。 |

对于缺少 CRS、空间范围异常或元数据互相矛盾的数据，必须先核对来源。系统可以提供显示兼容路径，但不应把“地图上看起来能对齐”视为科学上的空间对齐证明。

### 农业干旱分析边界

- 短期降水偏差、植被异常或温湿指标异常只能构成“干旱相关信号”；它们不自动等于作物损失。
- SPI、SPEI 等标准指标依赖明确的历史基准期、输入变量、算法实现和验证；不能以简单偏差替代。
- 公开数据受覆盖范围、更新时间、网络、许可和质量控制约束。
- 任何效率、精度、节水或增产结论，都应在真实对照与领域验证后报告。

## 快速开始

### 安装前准备

基础控制平面需要 Python 3.14+ 与 Git；完整 GEOINT 工作台还需要 **GDAL/OGR**。GDAL 是 GeoTIFF 检查与显示预处理、Shapefile 读取/转换的实际依赖，不安装它时，相关导入能力会给出明确的不可用提示。

| 安装目标 | Python 包组 | 是否需要 GDAL/OGR |
| --- | --- | --- |
| 仅 Angelus 控制平面 | 默认依赖 | 否 |
| 浏览器 GEOINT 工作台 | `geoint` | 是 |
| 开发与回归测试 | `geoint,test` | 是 |
| Tauri 桌面打包 | `geoint,desktop` | 是 |
| 精确 PostGIS 几何求交 | `postgis` | 另需可用的 PostGIS 服务 |

推荐先创建隔离环境：

```bash
git clone --recurse-submodules https://github.com/LunaticLegacy/angelus-geoint.git
cd angelus-geoint

python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
```

### 安装 GEOINT 工作台（推荐）

```bash
# 安装 LLMFetcher 子模块、Angelus 与 GDAL/OGR Python 绑定
python -m pip install --no-build-isolation -e ./llmfetcher
python -m pip install --no-build-isolation -e ".[geoint]"

# 验证 GDAL/OGR 是否可用
python -c "from osgeo import gdal, ogr; print(gdal.VersionInfo('--version'))"
```

`GDAL` 在支持的平台上会由 pip 安装二进制 wheel。若 pip 因本机 Python 版本或平台没有可用 wheel 而构建失败，请先安装与系统相匹配的 GDAL 开发包，再安装**同版本** Python 绑定：

```bash
# Debian / Ubuntu 示例
sudo apt install gdal-bin libgdal-dev
python -m pip install "GDAL==$(gdal-config --version)"
python -m pip install --no-build-isolation -e ./llmfetcher -e ".[geoint]"
```

不要把系统 `python3-gdal` 与虚拟环境中的任意版本混用；`gdal-config --version`、`python -c "from osgeo import gdal; ..."` 与 `pip show GDAL` 应反映同一套绑定版本。Windows 推荐使用与 Python 版本匹配的 GDAL wheel；若不存在 wheel，可使用 Conda-forge 环境安装 `gdal` 后再执行本项目的 editable install。

### 开发、测试与桌面打包依赖

```bash
# 开发环境：包含 GDAL/OGR 和 pytest
python -m pip install --no-build-isolation -r requirements.txt

# Tauri Python sidecar：包含 GDAL/OGR 和 PyInstaller，但不包含 pytest
python -m pip install --no-build-isolation -r requirements-desktop.txt

# 可选：仅在需要 PostGIS 精确几何求交时安装驱动
python -m pip install -e ".[postgis]"
```

前端或桌面开发还需要 Node.js 18+；发起真实智能体调查还需要可访问的模型服务及其 API Key。

### 启动浏览器工作台

```bash
angelus web --host 127.0.0.1 --port 8765
```

浏览器访问 <http://127.0.0.1:8765>，然后：

1. 创建会话，默认工作空间位于该会话的受控目录中；
2. 保存并绑定模型连接器；
3. 在图层面板导入边界、栅格或 Shapefile；
4. 检查图层范围与数据可用性，再发起明确的调查问题；
5. 在地图、执行追踪和证据面板中复核结果。

### 构建前端与桌面应用

```bash
npm install
npm run build:geoint

# Tauri 开发与打包
python -m pip install -r requirements-desktop.txt
npm run dev
npm run build
```

`src-tauri/target/` 是可删除的编译缓存；真正的发布物位于 Tauri 的 `target/release/bundle/` 输出中。不要把整个编译目录作为附件或安装包提交。

## 开发与测试

```bash
# 后端测试
python -m unittest discover -s tests

# GEOINT 前端测试
npm run test:geoint

# Tauri 壳编译检查
cargo check --manifest-path src-tauri/Cargo.toml
```

主要目录：

```text
angelus/              Angelus 控制平面、会话与 API
angelus/geoint/       GEOINT 领域服务：资产、导入、地图、处理与工具
frontend/geoint-src/  OpenLayers 工作台模块源码
frontend/static/      SPA 壳及构建产物
src-tauri/            桌面壳、原生导入桥接与打包配置
llmfetcher/           Agent 运行时子模块
tests/                后端回归测试
docs/                 设计、架构、参赛材料与安全文档
```

仓库导航可从 [INDEX.md](INDEX.md) 开始；GEOINT 领域设计见 [angelus/geoint/INDEX.md](angelus/geoint/INDEX.md)，竞赛说明与交付边界见 [docs/参赛方案.md](docs/参赛方案.md)。

## 许可证

本仓库许可证继承自 [Angelus](https://github.com/LunaticLegacy/angelus.git)， 采用 **AGPL-3.0-or-later**，并保留独立商业授权路径。详见 [LICENSING.md](LICENSING.md) 与 [commercial-licensing.md](commercial-licensing.md)。`llmfetcher` 为独立子模块，遵循其自身的版权与许可证声明。
