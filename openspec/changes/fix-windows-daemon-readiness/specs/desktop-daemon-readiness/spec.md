## ADDED Requirements

### Requirement: Windows packaged sidecar readiness
The Windows desktop shell SHALL accept a packaged daemon whose metadata mode is `tauri-sidecar` when the existing application identity, ready status, loopback URL, and live health checks pass, even when the daemon PID differs from the PyInstaller wrapper PID returned at spawn time.

#### Scenario: PyInstaller child publishes ready metadata
- **WHEN** the Windows desktop shell spawns a PyInstaller wrapper and its child daemon publishes valid ready metadata with a different PID
- **THEN** the shell accepts the daemon before the readiness timeout and navigates to its validated loopback URL

#### Scenario: Metadata has the wrong mode
- **WHEN** a spawned Windows daemon candidate publishes metadata whose mode is not `tauri-sidecar`
- **THEN** the shell does not accept that metadata as the owned sidecar

#### Scenario: Health validation fails
- **WHEN** Windows sidecar metadata claims readiness but the constrained loopback health endpoint does not return the expected application and ready status
- **THEN** the shell does not accept the daemon as ready

### Requirement: Unix sidecar process identity
The desktop shell on non-Windows platforms SHALL continue to require the metadata PID to equal the spawned sidecar PID or identify a descendant process.

#### Scenario: Unrelated Unix process publishes metadata
- **WHEN** valid-looking sidecar metadata on a non-Windows platform identifies neither the spawned process nor its descendant
- **THEN** the shell rejects that metadata for the owned sidecar

### Requirement: Windows metadata path fallback
The desktop shell SHALL use `MUSIC_DL_CONFIG_DIR` when non-empty, otherwise use `HOME/.config/music-dl`, and on Windows SHALL fall back to `HOMEDRIVE` plus `HOMEPATH` when `HOME` is unavailable.

#### Scenario: Windows HOME is unavailable
- **WHEN** `MUSIC_DL_CONFIG_DIR` and `HOME` are unset but `HOMEDRIVE` and `HOMEPATH` are present
- **THEN** the shell reads `daemon.json` from `<HOMEDRIVE><HOMEPATH>\.config\music-dl`

#### Scenario: Explicit config directory is set
- **WHEN** `MUSIC_DL_CONFIG_DIR` contains a non-empty path
- **THEN** the shell reads `daemon.json` from that path regardless of home-directory variables
