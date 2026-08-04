# Windows Daemon Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the packaged Windows desktop app accept its healthy PyInstaller child daemon without weakening Unix process-identity checks.

**Architecture:** Keep daemon supervision in the existing Tauri module. Use compile-time platform branches: Windows trusts only fully validated `tauri-sidecar` metadata and health, while Unix retains PID ancestry. Add one pure path-selection helper so Windows environment fallback is testable without mutating global environment variables.

**Tech Stack:** Rust 1.77+, Tauri 2, Python/PyInstaller sidecar, OpenSpec, GitHub Actions, Windows 11 PLEX-MINI test host.

---

## 1. Add Failing Regression Tests

**Files:**
- Modify and test: `tidaldl-py/src-tauri/src/lib.rs:104`
- Modify and test: `tidaldl-py/src-tauri/src/lib.rs:803`
- Modify: `.github/workflows/build-desktop.yml:52-61`

- [x] 1.1 Replace the existing sidecar metadata test with shared fixtures and platform-specific expectations:

```rust
fn sample_sidecar_metadata(pid: u32, mode: &str) -> DaemonMetadata {
    DaemonMetadata {
        app: APP_NAME.to_string(),
        status: READY_STATUS.to_string(),
        pid,
        base_url: "http://127.0.0.1:8766".to_string(),
        health_url: "http://127.0.0.1:8766/api/server/health".to_string(),
        mode: mode.to_string(),
    }
}

#[test]
fn sidecar_metadata_rejects_wrong_mode() {
    let meta = sample_sidecar_metadata(123, BROWSER_MODE);
    assert!(!sidecar_metadata_matches(&meta, 123));
}

#[cfg(not(windows))]
#[test]
fn sidecar_metadata_requires_matching_pid_on_unix() {
    let meta = sample_sidecar_metadata(123, SIDECAR_MODE);
    assert!(sidecar_metadata_matches(&meta, 123));
    assert!(!sidecar_metadata_matches(&meta, 456));
}

#[cfg(windows)]
#[test]
fn sidecar_metadata_accepts_pyinstaller_child_pid_on_windows() {
    let meta = sample_sidecar_metadata(123, SIDECAR_MODE);
    assert!(sidecar_metadata_matches(&meta, 456));
}
```

- [x] 1.2 Add Rust tests to the existing desktop build matrix after platform sidecar setup and before packaging:

```yaml
- name: Test Rust desktop shell
  run: cargo test --manifest-path src-tauri/Cargo.toml --target ${{ matrix.target }}
```

- [x] 1.3 Commit and push only the sidecar test plus workflow step, dispatch `build-desktop.yml` for `codex/fix-windows-daemon-readiness`, and record the Windows job failure before adding the path test or implementation.

```bash
rtk git add tidaldl-py/src-tauri/src/lib.rs .github/workflows/build-desktop.yml openspec/changes/fix-windows-daemon-readiness/tasks.md
rtk git commit -m "test(desktop): cover Windows sidecar child" -m "Refs #103"
rtk git push -u origin codex/fix-windows-daemon-readiness
rtk gh workflow run build-desktop.yml --ref codex/fix-windows-daemon-readiness
rtk gh run list --workflow build-desktop.yml --branch codex/fix-windows-daemon-readiness --limit 1 --json databaseId,status,conclusion,url
```

Expected: Windows job reaches and fails `sidecar_metadata_accepts_pyinstaller_child_pid_on_windows`; macOS and Linux Rust tests pass. Preserve the returned `databaseId` and evidence URL in task notes.

Harness correction: [run 30950767351](https://github.com/alfdav/music-dl/actions/runs/30950767351) and its [Windows job 92131978637](https://github.com/alfdav/music-dl/actions/runs/30950767351/job/92131978637) are not accepted as red proof. The test step ran before PyInstaller created `music-dl-server-x86_64-pc-windows-msvc.exe`, so Tauri's build script failed before executing tests. The test step was moved after platform sidecar setup; task 1.3 remains incomplete until the Windows assertion itself fails.

Accepted red proof: [run 30951212136](https://github.com/alfdav/music-dl/actions/runs/30951212136), [Windows job 92133463673](https://github.com/alfdav/music-dl/actions/runs/30951212136/job/92133463673), commit `c462b10`. The sidecar build passed; Rust executed 11 tests, 10 passed, and only `sidecar_metadata_accepts_pyinstaller_child_pid_on_windows` failed because `sidecar_metadata_matches(&meta, 456)` returned false.

- [x] 1.4 After recording the Windows PID failure, add pure path-selection tests in the same Rust test module:

```rust
#[test]
fn daemon_home_prefers_home() {
    let path = resolve_daemon_home(
        Some("C:\\primary".to_string()),
        Some("D:".to_string()),
        Some("\\fallback".to_string()),
    )
    .unwrap();

    assert_eq!(path, PathBuf::from("C:\\primary"));
}

#[test]
fn daemon_home_uses_windows_parts_without_home() {
    let path = resolve_daemon_home(
        None,
        Some("C:".to_string()),
        Some("\\Users\\tester".to_string()),
    )
    .unwrap();

    assert_eq!(path, PathBuf::from("C:\\Users\\tester"));
}
```

- [x] 1.5 Run the focused Rust tests locally and verify the new path tests fail before implementation:

```bash
rtk cargo test --manifest-path tidaldl-py/src-tauri/Cargo.toml daemon_home
```

Expected: compilation fails because `resolve_daemon_home` does not exist. This is the independent red proof for path fallback.

Observed: `cargo test` exited 101 with two `E0425` errors at the new tests because `resolve_daemon_home` did not exist. No production code had been added.

## 2. Implement Minimum Platform Fix

**Files:**
- Modify: `tidaldl-py/src-tauri/src/lib.rs:104-149`
- Test: `tidaldl-py/src-tauri/src/lib.rs:706-822`

- [x] 2.1 Restrict Unix process inspection to non-Windows builds and branch sidecar identity by platform:

```rust
#[cfg(not(windows))]
fn process_parent_pid(pid: u32) -> Option<u32> {
    // Keep existing implementation unchanged.
}

#[cfg(not(windows))]
fn process_has_ancestor(mut pid: u32, ancestor: u32) -> bool {
    // Keep existing implementation unchanged.
}

fn sidecar_metadata_matches(meta: &DaemonMetadata, spawned_pid: u32) -> bool {
    if meta.mode != SIDECAR_MODE {
        return false;
    }

    #[cfg(windows)]
    {
        let _ = spawned_pid;
        true
    }

    #[cfg(not(windows))]
    {
        meta.pid == spawned_pid || process_has_ancestor(meta.pid, spawned_pid)
    }
}
```

- [x] 2.2 Add the pure home resolver immediately before `daemon_metadata_path`:

```rust
fn resolve_daemon_home(
    home: Option<String>,
    home_drive: Option<String>,
    home_path: Option<String>,
) -> Result<PathBuf, String> {
    if let Some(home) = home.filter(|value| !value.trim().is_empty()) {
        return Ok(PathBuf::from(home));
    }

    match (home_drive, home_path) {
        (Some(drive), Some(path)) if !drive.trim().is_empty() && !path.trim().is_empty() => {
            Ok(PathBuf::from(format!("{drive}{path}")))
        }
        _ => Err("HOME is not set".to_string()),
    }
}
```

- [x] 2.3 Replace the direct `HOME` read in `daemon_metadata_path` while preserving the explicit config override:

```rust
#[cfg(windows)]
let (home_drive, home_path) = (
    std::env::var("HOMEDRIVE").ok(),
    std::env::var("HOMEPATH").ok(),
);
#[cfg(not(windows))]
let (home_drive, home_path) = (None, None);

let home = resolve_daemon_home(std::env::var("HOME").ok(), home_drive, home_path)?;
Ok(home.join(".config").join(APP_NAME).join("daemon.json"))
```

- [x] 2.4 Run the focused tests and verify they pass:

```bash
rtk cargo test --manifest-path tidaldl-py/src-tauri/Cargo.toml daemon_home
rtk cargo test --manifest-path tidaldl-py/src-tauri/Cargo.toml sidecar_metadata
```

Expected: all selected tests pass on macOS; Windows test compiles and passes in the Windows CI job.

## 3. Correct Support Documentation

**Files:**
- Modify: `.github/ISSUE_TEMPLATE/bug-report.yml:117`
- Modify: `docs/bug-reporting.md:43`

- [x] 3.1 Replace the incorrect Windows config location:

```yaml
- Windows: `%USERPROFILE%\.config\music-dl\`
```

- [x] 3.2 Verify no tracked documentation still claims the runtime uses `%APPDATA%\music-dl`:

```bash
rtk rg -n --hidden -F '%APPDATA%\music-dl' --glob '*.md' --glob '*.yml' --glob '*.yaml' --glob '!openspec/**'
```

Expected: no stale runtime-path claim.

## 4. Verify and Review Locally

**Files:**
- Update task checkboxes: `openspec/changes/fix-windows-daemon-readiness/tasks.md`

- [x] 4.1 Run the complete Rust suite:

```bash
rtk cargo test --manifest-path tidaldl-py/src-tauri/Cargo.toml
```

Expected: all Rust tests pass.

- [x] 4.2 Run repository checks relevant to the changed documentation and release metadata:

```bash
cd tidaldl-py
rtk uv run --extra test python -m pytest tests/test_packaging.py tests/test_static_assets.py -q
cd ..
rtk uv run python scripts/release_version.py check
rtk openspec validate fix-windows-daemon-readiness --strict
```

Expected: all checks pass and OpenSpec remains valid.

- [x] 4.2a Repair the pre-existing split-GUI asset-check drift exposed by green [run 30951864618](https://github.com/alfdav/music-dl/actions/runs/30951864618): Windows Rust tests passed, but `Verify bundled assets (Windows)` failed because deleted `static/app.js` was still referenced. Reuse `tests/test_static_assets.py` in CI, reuse `tests.gui_js_source.read_gui_js` in the local Tauri build command, and correct the stale local-lyrics link.

- [x] 4.3 Invoke `ponytail:ponytail-review` on the final diff. Remove any new module, dependency, speculative diagnostic layer, or duplicated path logic.

- [x] 4.4 Commit the implementation and documentation together:

```bash
rtk git add tidaldl-py/src-tauri/src/lib.rs .github/ISSUE_TEMPLATE/bug-report.yml docs/bug-reporting.md openspec/changes/fix-windows-daemon-readiness/design.md openspec/changes/fix-windows-daemon-readiness/proposal.md openspec/changes/fix-windows-daemon-readiness/tasks.md
rtk git commit -m "fix(desktop): accept Windows sidecar child" -m "Refs #103"
```

## 5. Verify Packaged Windows Behavior

**Files and systems:**
- GitHub workflow: `.github/workflows/build-desktop.yml`
- Test host: `plex-mini` (`100.91.244.11`)
- Protected boundary: do not reboot or operate Hyper-V VMs, VM networking, or VM storage.

Recorded pre-test state on 2026-08-03: no desktop package, `%USERPROFILE%\.config\music-dl`, or `%TEMP%\music-dl-issue-103` existed. The controlled v1.6.8 reproduction created only that package and those two paths. Cleanup below requires version, expected-file, and ownership-marker checks before removal.

- [ ] 5.1 Push the implementation commit and rerun the existing workflow for the branch:

```bash
rtk git push origin codex/fix-windows-daemon-readiness
rtk gh workflow run build-desktop.yml --ref codex/fix-windows-daemon-readiness
rtk gh run list --workflow build-desktop.yml --branch codex/fix-windows-daemon-readiness --limit 1 --json databaseId,status,conclusion,url
```

Use the returned `databaseId` with `rtk gh run watch <databaseId> --exit-status`. Expected: Windows Rust tests pass and the Windows packaging job succeeds.

- [ ] 5.2 Download only the Windows artifact into ignored `output/` and compute its SHA-256:

```bash
rtk gh run download <databaseId> -n music-dl-windows-x86_64 -D output/issue-103/windows
rtk shasum -a 256 output/issue-103/windows/*.msi
```

Execute this PowerShell through SSH `-EncodedCommand`; it refuses to reuse an unknown directory and leaves an ownership marker:

```powershell
$TestDir = Join-Path $env:TEMP 'music-dl-issue-103-fixed'
if (Test-Path -LiteralPath $TestDir) { throw "Refusing existing test directory: $TestDir" }
New-Item -ItemType Directory -Path $TestDir | Out-Null
Set-Content -LiteralPath (Join-Path $TestDir '.issue-103-owned') -Value 'created-by-issue-103'
```

Only after that succeeds, transfer the MSI:

```bash
rtk proxy scp output/issue-103/windows/*.msi plex-mini:'C:/Users/PLEX-MINI/AppData/Local/Temp/music-dl-issue-103-fixed/'
```

Record the local SHA-256. After `scp`, run `Get-FileHash -Algorithm SHA256` against the transferred MSI and require the same value before installation.

- [ ] 5.3 Before replacement, verify the two baseline paths contain only controlled-test files, then mark them as owned:

```powershell
$BaselineDir = Join-Path $env:TEMP 'music-dl-issue-103'
$BaselineConfig = Join-Path $env:USERPROFILE '.config\music-dl'
$AllowedTemp = @('music-dl_1.6.8_x64_en-US.msi','install.log','app.stdout.log','app.stderr.log')
$AllowedConfig = @('daemon.json','library.db','library.db-shm','library.db-wal','token.json')
$UnexpectedTemp = Get-ChildItem -LiteralPath $BaselineDir -File | Where-Object Name -notin $AllowedTemp
$UnexpectedConfig = Get-ChildItem -LiteralPath $BaselineConfig -File | Where-Object Name -notin $AllowedConfig
if ($UnexpectedTemp -or $UnexpectedConfig) { throw 'Unexpected data found in recorded test paths; refusing cleanup ownership' }
Set-Content -LiteralPath (Join-Path $BaselineDir '.issue-103-owned') -Value 'created-by-issue-103'
Set-Content -LiteralPath (Join-Path $BaselineConfig '.issue-103-owned') -Value 'created-by-issue-103'
```

Then replace only the test-installed package using non-restarting, logged MSI operations:

```powershell
$ErrorActionPreference = 'Stop'
$TestDir = Join-Path $env:TEMP 'music-dl-issue-103-fixed'
$BaseLog = Join-Path $TestDir 'uninstall-v1.6.8.log'
$InstallLog = Join-Path $TestDir 'install-fixed.log'
$Msi = Get-ChildItem -LiteralPath $TestDir -Filter '*.msi' | Select-Object -First 1
$Installed = @(Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' |
  Where-Object { $_.DisplayName -eq 'music-dl' })
if ($Installed.Count -ne 1 -or $Installed[0].DisplayVersion -ne '1.6.8' -or $Installed[0].InstallLocation -ne 'C:\Program Files\music-dl\') {
  throw 'Refusing to replace anything except the recorded v1.6.8 test install'
}
$Exit = (Start-Process msiexec.exe -ArgumentList @('/x', $Installed[0].PSChildName, '/qn', '/norestart', '/L*v', $BaseLog) -Wait -PassThru).ExitCode
if ($Exit -ne 0) { throw "Baseline uninstall failed: $Exit" }
$Exit = (Start-Process msiexec.exe -ArgumentList @('/i', $Msi.FullName, '/qn', '/norestart', '/L*v', $InstallLog) -Wait -PassThru).ExitCode
if ($Exit -ne 0) { throw "Fixed MSI install failed: $Exit" }
```

- [ ] 5.4 Create an isolated launcher and run it in the already-active `plex-mini` console session without touching Hyper-V:

```powershell
$TestDir = Join-Path $env:TEMP 'music-dl-issue-103-fixed'
$ConfigDir = Join-Path $TestDir 'config'
$Launcher = Join-Path $TestDir 'launch-fixed.cmd'
@"
@echo off
set MUSIC_DL_CONFIG_DIR=$ConfigDir
"C:\Program Files\music-dl\music-dl.exe"
"@ | Set-Content -LiteralPath $Launcher -Encoding ASCII

$TaskName = 'music-dl-issue-103-fixed'
schtasks.exe /Create /TN $TaskName /SC ONCE /ST 00:00 /TR "`"$Launcher`"" /IT /F
if ($LASTEXITCODE -ne 0) { throw 'Scheduled-task creation failed' }
schtasks.exe /Run /TN $TaskName
if ($LASTEXITCODE -ne 0) { throw 'Scheduled-task launch failed' }
```

- [ ] 5.5 Over SSH, run this exact PowerShell through `-EncodedCommand` to sample `music-dl.exe`, both PyInstaller PIDs, isolated `daemon.json`, and `/api/server/health` every five seconds through 35 seconds:

```powershell
$ErrorActionPreference = 'Stop'
$TestDir = Join-Path $env:TEMP 'music-dl-issue-103-fixed'
$ConfigDir = Join-Path $TestDir 'config'
$Log = Join-Path $TestDir 'readiness.log'
Remove-Item -LiteralPath $Log -Force -ErrorAction SilentlyContinue
for ($Index = 0; $Index -le 7; $Index++) {
  "SNAPSHOT_SECONDS=$($Index * 5)" | Out-File -LiteralPath $Log -Append
  Get-CimInstance Win32_Process |
    Where-Object { $_.Name -in @('music-dl.exe','music-dl-server.exe') } |
    Select-Object Name,ProcessId,ParentProcessId,ExecutablePath,CommandLine |
    Format-List | Out-File -LiteralPath $Log -Append
  $DaemonPath = Join-Path $ConfigDir 'daemon.json'
  "DAEMON_EXISTS=$(Test-Path -LiteralPath $DaemonPath)" | Out-File -LiteralPath $Log -Append
  if (Test-Path -LiteralPath $DaemonPath) {
    $Metadata = Get-Content -LiteralPath $DaemonPath -Raw | ConvertFrom-Json
    $Metadata | ConvertTo-Json -Compress | Out-File -LiteralPath $Log -Append
    try {
      Invoke-RestMethod -Uri $Metadata.health_url -TimeoutSec 2 |
        ConvertTo-Json -Compress | Out-File -LiteralPath $Log -Append
    } catch {
      "HEALTH_ERROR=$($_.Exception.Message)" | Out-File -LiteralPath $Log -Append
    }
  }
  if ($Index -lt 7) { Start-Sleep -Seconds 5 }
}
Get-Content -LiteralPath $Log
```

Expected by five seconds:

- `daemon.json` reports `status: ready` and `mode: tauri-sidecar`.
- Tauri remains attached to the application instead of entering its timeout path.
- At 35 seconds the desktop app and daemon remain healthy.

- [ ] 5.6 Stop only `music-dl` test processes, verify both PyInstaller PIDs exit, then uninstall the fixed MSI:

```powershell
$Desktop = Get-Process -Name 'music-dl' -ErrorAction Stop
if (-not $Desktop.CloseMainWindow()) { throw 'Could not close desktop window normally' }
$Desktop | Wait-Process -Timeout 10
Start-Sleep -Seconds 3
if (Get-Process -Name 'music-dl-server' -ErrorAction SilentlyContinue) {
  Get-Process -Name 'music-dl-server' | Stop-Process -Force
  throw 'music-dl-server remained orphaned after desktop shutdown'
}
$Installed = Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' |
  Where-Object { $_.DisplayName -eq 'music-dl' }
if ($Installed) {
  $Log = Join-Path $env:TEMP 'music-dl-issue-103-fixed\uninstall-fixed.log'
  $Exit = (Start-Process msiexec.exe -ArgumentList @('/x', $Installed.PSChildName, '/qn', '/norestart', '/L*v', $Log) -Wait -PassThru).ExitCode
  if ($Exit -ne 0) { throw "Fixed MSI uninstall failed: $Exit" }
}
```

- [ ] 5.7 Copy evidence off PLEX-MINI before cleanup:

```bash
rtk proxy scp plex-mini:'C:/Users/PLEX-MINI/AppData/Local/Temp/music-dl-issue-103-fixed/readiness.log' output/issue-103/readiness.log
rtk proxy scp plex-mini:'C:/Users/PLEX-MINI/AppData/Local/Temp/music-dl-issue-103-fixed/*.log' output/issue-103/windows-logs/
```

- [ ] 5.8 Delete the exact scheduled task and only directories carrying the issue-owned marker:

```powershell
$TaskName = 'music-dl-issue-103-fixed'
schtasks.exe /Delete /TN $TaskName /F
$FixedDir = Join-Path $env:TEMP 'music-dl-issue-103-fixed'
$BaselineDir = Join-Path $env:TEMP 'music-dl-issue-103'
$BaselineConfig = Join-Path $env:USERPROFILE '.config\music-dl'
foreach ($Path in @($FixedDir, $BaselineDir, $BaselineConfig)) {
  if (Test-Path -LiteralPath $Path) {
    $Marker = Join-Path $Path '.issue-103-owned'
    if (-not (Test-Path -LiteralPath $Marker)) { throw "Refusing unowned cleanup target: $Path" }
    Remove-Item -LiteralPath $Path -Recurse -Force
  }
}
```

Leave legacy `tidal-dl.exe`, Hyper-V VMs, VM networking, VM storage, and all unrelated host paths untouched.

- [ ] 5.9 Record exact Windows red/green workflow URLs and packaged readiness evidence in task notes, then run final `rtk openspec validate fix-windows-daemon-readiness --strict`.
