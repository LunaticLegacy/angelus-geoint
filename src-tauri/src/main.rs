#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    env,
    fs::File,
    io::{self, Read, Write},
    net::{TcpListener, TcpStream},
    path::PathBuf,
    process::{Child, Command, Stdio},
    collections::HashSet,
    sync::Mutex,
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use serde_json::{json, Value};
use tauri::{DragDropEvent, Emitter, Manager, WebviewUrl, WebviewWindowBuilder, WindowEvent};
use tauri_plugin_dialog::DialogExt;

/// Owns the Python child process for the lifetime of the desktop window.
struct BackendProcess(Child);

/// Desktop-only, short-lived import coordination. It owns the native paths;
/// WebView JavaScript receives only filenames, progress and import snapshots.
struct DesktopImportState {
    backend_port: u16,
    selected_session: Mutex<Option<String>>,
}

impl Drop for BackendProcess {
    /// Stop the local FastAPI process when the Tauri application exits.
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

/// Pick an ephemeral localhost port so another local service cannot block startup.
fn reserve_port() -> Result<u16, String> {
    let listener = TcpListener::bind(("127.0.0.1", 0)).map_err(|error| error.to_string())?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|error| error.to_string())
}

/// Resolve the persistent backend state directory.
///
/// Desktop builds store sessions and connectors under the per-user app data
/// directory so research traces survive application restarts.  An explicit
/// ``ANGELUS_STATE_DIR`` always wins and is used by tests and scripting.
fn backend_state_dir(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    if let Ok(dir) = env::var("ANGELUS_STATE_DIR") {
        return Ok(PathBuf::from(dir));
    }
    app.path()
        .app_data_dir()
        .map(|dir| dir.join("workspace"))
        .map_err(|error| format!("unable to resolve app data directory: {error}"))
}

/// Resolve the packaged sidecar, or use the explicit executable for development.
fn backend_command(app: &tauri::AppHandle, port: u16) -> Result<Command, String> {
    let mut command = if let Ok(executable) = env::var("ANGELUS_BACKEND_EXECUTABLE") {
        Command::new(executable)
    } else if cfg!(debug_assertions) {
        let mut command = Command::new("python");
        command.args(["-m", "angelus", "web"]);
        command.current_dir(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(".."));
        command
    } else {
        let resource = app
            .path()
            .resource_dir()
            .map_err(|error| error.to_string())?
            .join("binaries")
            .join(if cfg!(windows) {
                "angelus-backend.exe"
            } else {
                "angelus-backend"
            });
        Command::new(resource)
    };

    // Keep the backend loopback-only; the desktop webview is its only client.
    command.args(["--host", "127.0.0.1", "--port", &port.to_string()]);

    // Pin backend state to a stable directory. Packaged PyInstaller
    // ``--onefile`` sidecars run from a temporary extraction directory, so
    // the backend's default project-local ``workspace`` would otherwise be
    // wiped on every exit. Set the canonical Angelus name and its legacy
    // LLMFetcher alias together, matching `angelus --state-dir`.
    if cfg!(debug_assertions) {
        if let Ok(dir) = env::var("ANGELUS_STATE_DIR") {
            command.env("ANGELUS_STATE_DIR", &dir);
            command.env("LLMFETCHER_STATE_DIR", dir);
        }
    } else {
        let dir = backend_state_dir(app)?;
        command.env("ANGELUS_STATE_DIR", &dir);
        command.env("LLMFETCHER_STATE_DIR", &dir);
    }

    command
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::inherit());
    Ok(command)
}

/// Start the backend and wait until its HTTP socket accepts connections.
fn start_backend(app: &tauri::AppHandle, port: u16) -> Result<Child, String> {
    let mut child = backend_command(app, port)?
        .spawn()
        .map_err(|error| format!("unable to start Angelus backend: {error}"))?;
    for _ in 0..100 {
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return Ok(child);
        }
        if let Ok(Some(status)) = child.try_wait() {
            return Err(format!("Angelus backend exited during startup: {status}"));
        }
        thread::sleep(Duration::from_millis(50));
    }
    let _ = child.kill();
    Err("timed out waiting for the Angelus backend".to_string())
}

fn valid_session_id(value: &str) -> bool {
    !value.is_empty() && value.len() <= 80 && !value.contains('/') && !value.contains('\\')
}

/// Mirror selected-session state into the desktop shell without giving the
/// frontend any filesystem capability.
#[tauri::command]
fn set_geoint_import_session(
    state: tauri::State<'_, DesktopImportState>,
    session_id: Option<String>,
) -> Result<(), String> {
    if let Some(value) = session_id.as_deref() {
        if !valid_session_id(value) {
            return Err("invalid import session".into());
        }
    }
    *state
        .selected_session
        .lock()
        .map_err(|_| "desktop import state is unavailable")? = session_id;
    Ok(())
}

/// Select GIS files through the host operating system's file chooser.
///
/// Paths remain inside the desktop shell.  They are immediately handed to the
/// existing path-safe desktop upload flow, which publishes only progress and
/// inspection snapshots back to the WebView.
#[tauri::command]
async fn choose_geoint_import_files(
    app: tauri::AppHandle,
    state: tauri::State<'_, DesktopImportState>,
) -> Result<bool, String> {
    let session_id = state
        .selected_session
        .lock()
        .map_err(|_| "desktop import state is unavailable")?
        .clone()
        .ok_or("请先选择会话，再导入数据")?;
    let port = state.backend_port;
    let files = app
        .dialog()
        .file()
        .add_filter("GEOINT 数据", &["geojson", "json", "tif", "tiff", "shp", "shx", "dbf", "prj", "cpg"])
        .add_filter("全部文件", &["*"])
        .blocking_pick_files();
    let Some(files) = files else { return Ok(false); };
    let paths = files
        .into_iter()
        .filter_map(|file| file.into_path().ok())
        .collect::<Vec<_>>();
    if paths.is_empty() { return Ok(false); }
    thread::spawn(move || desktop_import(app, port, session_id, paths));
    Ok(true)
}

/// Open only the selected session's registered workspace with the host file
/// manager.  The WebView never supplies a filesystem path to this command.
#[tauri::command]
fn open_geoint_workspace(
    state: tauri::State<'_, DesktopImportState>,
) -> Result<(), String> {
    let session_id = state
        .selected_session
        .lock()
        .map_err(|_| "desktop import state is unavailable")?
        .clone()
        .ok_or("请先选择会话")?;
    let sessions = json_request(state.backend_port, "GET", "/api/sessions", json!({}))?;
    let project_path = sessions["sessions"]
        .as_array()
        .and_then(|items| items.iter().find(|item| item["id"].as_str() == Some(session_id.as_str())))
        .and_then(|item| item["project_path"].as_str())
        .map(PathBuf::from)
        .ok_or("当前会话没有可打开的工作空间")?;
    if !project_path.is_dir() { return Err("当前会话工作空间不存在或不可访问".into()); }
    #[cfg(target_os = "windows")]
    let mut command = { let mut value = Command::new("explorer"); value.arg(&project_path); value };
    #[cfg(target_os = "macos")]
    let mut command = { let mut value = Command::new("open"); value.arg(&project_path); value };
    #[cfg(all(unix, not(target_os = "macos")))]
    let mut command = { let mut value = Command::new("xdg-open"); value.arg(&project_path); value };
    command.spawn().map_err(|error| format!("无法打开系统文件管理器：{error}"))?;
    Ok(())
}

fn response_body(mut stream: TcpStream) -> Result<Value, String> {
    let mut text = String::new();
    stream
        .read_to_string(&mut text)
        .map_err(|error| error.to_string())?;
    let (head, body) = text
        .split_once("\r\n\r\n")
        .ok_or("invalid backend response")?;
    let status = head.lines().next().unwrap_or_default();
    if !status.contains(" 2") {
        return Err(format!("desktop import backend request failed: {body}"));
    }
    serde_json::from_str(body).map_err(|error| format!("invalid backend JSON: {error}"))
}

fn json_request(port: u16, method: &str, path: &str, body: Value) -> Result<Value, String> {
    let encoded = serde_json::to_vec(&body).map_err(|error| error.to_string())?;
    let mut stream = TcpStream::connect(("127.0.0.1", port)).map_err(|error| error.to_string())?;
    let request = format!(
        "{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n",
        encoded.len()
    );
    stream
        .write_all(request.as_bytes())
        .and_then(|_| stream.write_all(&encoded))
        .map_err(|error| error.to_string())?;
    response_body(stream)
}

fn file_request(port: u16, path: &str, source: &PathBuf, length: u64) -> Result<Value, String> {
    let mut stream = TcpStream::connect(("127.0.0.1", port)).map_err(|error| error.to_string())?;
    let request = format!(
        "PUT {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\nContent-Type: application/octet-stream\r\nContent-Length: {length}\r\n\r\n"
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|error| error.to_string())?;
    let mut file = File::open(source).map_err(|error| error.to_string())?;
    io::copy(&mut file, &mut stream).map_err(|error| error.to_string())?;
    response_body(stream)
}

/// Expand a selected `.shp` into the sibling sidecar bundle required by OGR.
///
/// The native shell has host path authority, unlike a browser FileList.  It
/// can therefore include same-stem required members without asking an
/// operator to manually multi-select invisible companion files.  Other paths
/// are preserved; non-existent sidecars are intentionally left for the
/// importer to report as an actionable incomplete bundle.
fn expand_shapefile_members(paths: Vec<PathBuf>) -> Vec<PathBuf> {
    let mut seen = HashSet::new();
    let mut expanded = Vec::new();
    for path in paths {
        if seen.insert(path.clone()) { expanded.push(path.clone()); }
        if !path.extension().is_some_and(|suffix| suffix.eq_ignore_ascii_case("shp")) { continue; }
        let Some(parent) = path.parent() else { continue; };
        let Some(stem) = path.file_stem() else { continue; };
        for suffix in ["shx", "dbf", "prj", "cpg"] {
            let sibling = parent.join(stem).with_extension(suffix);
            if sibling.is_file() && seen.insert(sibling.clone()) { expanded.push(sibling); }
        }
    }
    expanded
}

fn desktop_import(app: tauri::AppHandle, port: u16, session_id: String, paths: Vec<PathBuf>) {
    let files: Vec<(PathBuf, String, u64)> = expand_shapefile_members(paths)
        .into_iter()
        .filter_map(|path| {
            let metadata = path.metadata().ok()?;
            if !metadata.is_file() {
                return None;
            }
            let name = path.file_name()?.to_str()?.to_owned();
            Some((path, name, metadata.len()))
        })
        .collect();
    if files.is_empty() {
        let _ = app.emit(
            "geoint://native-import",
            json!({"type": "error", "message": "未收到可导入的文件"}),
        );
        return;
    }
    let request_id = format!(
        "native-{}",
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis()
    );
    let start = json_request(
        port,
        "POST",
        &format!("/api/geoint/sessions/{session_id}/imports"),
        json!({
            "files": files.iter().map(|(_, name, length)| json!({"name": name, "size_bytes": length})).collect::<Vec<_>>(),
            "client_request_id": request_id,
        }),
    );
    let result = (|| -> Result<Value, String> {
        let mut snapshot = start?;
        let import_id = snapshot["import_id"]
            .as_str()
            .ok_or("backend omitted import id")?
            .to_owned();
        for (index, (path, name, length)) in files.iter().enumerate() {
            let file_id = snapshot["files"][index]["file_id"]
                .as_str()
                .ok_or("backend omitted upload file id")?;
            let _ = app.emit("geoint://native-import", json!({"type": "progress", "message": format!("正在导入 {name}…"), "index": index, "total": files.len()}));
            snapshot = file_request(
                port,
                &format!("/api/geoint/sessions/{session_id}/imports/{import_id}/files/{file_id}"),
                path,
                *length,
            )?;
        }
        let revision = snapshot["revision"]
            .as_i64()
            .ok_or("backend omitted import revision")?;
        json_request(
            port,
            "POST",
            &format!("/api/geoint/sessions/{session_id}/imports/{import_id}/inspect"),
            json!({"expected_revision": revision}),
        )
    })();
    match result {
        Ok(snapshot) => {
            let _ = app.emit(
                "geoint://native-import",
                json!({"type": "inspection", "snapshot": snapshot}),
            );
        }
        Err(message) => {
            let _ = app.emit(
                "geoint://native-import",
                json!({"type": "error", "message": format!("桌面导入失败：{message}")}),
            );
        }
    }
}

/// Launch the loopback FastAPI UI in a native Tauri window.
fn run() -> Result<(), Box<dyn std::error::Error>> {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            set_geoint_import_session,
            choose_geoint_import_files,
            open_geoint_workspace,
        ])
        .setup(|app| {
            let port = reserve_port().map_err(std::io::Error::other)?;
            let child = start_backend(app.handle(), port).map_err(std::io::Error::other)?;
            app.manage(BackendProcess(child));
            app.manage(DesktopImportState {
                backend_port: port,
                selected_session: Mutex::new(None),
            });
            let url = format!("http://127.0.0.1:{port}/").parse()?;
            let window = WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
                .title("Angelus · Agent Workbench")
                .inner_size(1440.0, 920.0)
                .min_inner_size(1024.0, 700.0)
                .build()?;
            let app_handle = app.handle().clone();
            window.on_window_event(move |event| {
                if let WindowEvent::DragDrop(DragDropEvent::Drop { paths, .. }) = event {
                    let state = app_handle.state::<DesktopImportState>();
                    let session_id = state
                        .selected_session
                        .lock()
                        .ok()
                        .and_then(|value| value.clone());
                    match session_id {
                        Some(session_id) => {
                            let port = state.backend_port;
                            let paths = paths.clone();
                            let app = app_handle.clone();
                            thread::spawn(move || desktop_import(app, port, session_id, paths));
                        }
                        None => {
                            let _ = app_handle.emit(
                                "geoint://native-import",
                                json!({"type": "error", "message": "请先选择会话，再拖入数据"}),
                            );
                        }
                    }
                }
            });
            Ok(())
        })
        .run(tauri::generate_context!())?;
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
