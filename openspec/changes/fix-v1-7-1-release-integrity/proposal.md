## Why

The v1.7.1 release candidate has three verified integrity failures: the loopback web UI cannot invoke desktop updater commands, local quality labels can disagree for the same file, and incomplete embedded tags can split one artist across multiple library groups. Shipping binaries with these faults would preserve broken update guidance and contradictory library facts.

## What Changes

- Grant the loopback UI only the desktop commands it already uses, without exposing sidecar process permissions.
- Persist detected audio codec and derive every local quality label from that codec.
- Resolve local display metadata once during scanning using meaningful embedded tags first and structured library paths second.
- Add focused regression coverage and update relevant library documentation.

## Capabilities

### New Capabilities

- `desktop-loopback-ipc`: The trusted loopback UI can invoke required desktop status, updater, and sidecar-control commands through a least-privilege Tauri capability.
- `local-audio-quality`: Local quality labels use persisted codec facts consistently in every view.
- `local-metadata-resolution`: Incomplete local tags use conservative path-derived display metadata without modifying audio files.

### Modified Capabilities

None.

## Impact

Changes affect Tauri capability configuration, local-library scanning and schema migration, shared GUI quality classification, focused tests, and library documentation. No audio file is rewritten. No new dependency or runtime service is added.
