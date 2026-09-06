fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(&[
                "set_geoint_import_session",
                "choose_geoint_import_files",
                "open_geoint_workspace",
            ])),
    )
    .expect("failed to build Tauri desktop capability manifest");
}
