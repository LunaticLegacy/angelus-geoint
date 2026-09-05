# src-tauri/ — Tauri Desktop Shell INDEX

Angelus 的 Tauri 2 桌面壳。它为本地 FastAPI 服务选择 loopback 端口、管理 Python sidecar 生命周期，并将 WebView 指向该服务。

| Entry | Type | Responsibility |
|---|---|---|
| `src/main.rs` | 预留本地端口、启动/回收后端进程并创建 Tauri WebView 窗口；从 Tauri 主窗口的 `WindowEvent::DragDrop` 接收桌面文件拖入，并仅在壳内向 loopback 导入 API 流式上传。 |
| `Cargo.toml` / `Cargo.lock` | Rust 包与锁定依赖；桌面 prerelease 版本为 `0.5.0-preview`。 |
| `tauri.conf.json` | 窗口、bundle、sidecar 资源和 CSP 配置；与发布标签 `v0.5.0-preview` 对应，WiX 使用数值版本 `0.5.0.0`。 |
| `capabilities/desktop-import.json` | 仅向本机 loopback 工作台授予导入会话同步命令和事件订阅权限；不授予文件系统或路径读取权限。 |
| `build.rs` | Tauri build-time 配置入口；显式生成最小自定义 IPC 命令的 allow/deny 权限清单。 |
| `binaries/` | `scripts/build-backend.mjs` / `build_backend.py` 生成的 Python sidecar 放置目录。 |
| `icons/` | 桌面应用图标源文件。 |

## Intent Routing

- **桌面生命周期与端口/进程管理** → `src/main.rs`
- **桌面原生拖入、字节上传与路径隔离** → `src/main.rs`；前端桥接 → `../frontend/geoint-src/native-import-bridge.js`
- **远程 loopback WebView 的最小 IPC 能力** → `capabilities/desktop-import.json`
- **打包、资源或 CSP** → `tauri.conf.json`
- **构建 Python sidecar** → `../scripts/INDEX.md`

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [build.rs](build.rs#L1) | `main` | `None` | `()` | Implement `main` in the desktop shell. |
| [src/main.rs](src/main.rs#L19) | `drop` | `&mut self` | `()` | Implement `drop` in the desktop shell. |
| [src/main.rs](src/main.rs#L26) | `reserve_port` | `None` | `Result<u16, String>` | Implement `reserve_port` in the desktop shell. |
| [src/main.rs](src/main.rs#L39) | `backend_state_dir` | `app: &tauri::AppHandle` | `Result<PathBuf, String>` | Implement `backend_state_dir` in the desktop shell. |
| [src/main.rs](src/main.rs#L50) | `backend_command` | `app: &tauri::AppHandle, port: u16` | `Result<Command, String>` | Implement `backend_command` in the desktop shell. |
| [src/main.rs](src/main.rs#L99) | `start_backend` | `app: &tauri::AppHandle, port: u16` | `Result<Child, String>` | Implement `start_backend` in the desktop shell. |
| [src/main.rs](src/main.rs#L117) | `run` | `None` | `Result<(), Box<dyn std::error::Error>>` | Implement `run` in the desktop shell. |
| [src/main.rs](src/main.rs#L134) | `main` | `None` | `()` | Implement `main` in the desktop shell. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [src/main.rs](src/main.rs#L15) | `BackendProcess` | `See declaration` | `struct` | Represent `BackendProcess` desktop-shell state. |

<!-- END GENERATED SYMBOL MAP -->
