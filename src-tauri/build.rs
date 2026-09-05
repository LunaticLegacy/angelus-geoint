fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(&["set_geoint_import_session"])),
    )
    .expect("failed to build Tauri desktop capability manifest");
}
