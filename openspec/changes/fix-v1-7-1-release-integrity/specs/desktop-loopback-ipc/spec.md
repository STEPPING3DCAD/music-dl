## ADDED Requirements

### Requirement: Trusted loopback UI can invoke desktop commands
The desktop application SHALL allow its `http://127.0.0.1:<port>` GUI to invoke the registered updater, status, and sidecar-control commands.

#### Scenario: Loopback GUI checks updater state
- **WHEN** the main window loaded from an arbitrary loopback port invokes `get_updater_state`
- **THEN** Tauri authorizes the command and returns its runtime result rather than an ACL rejection

#### Scenario: Unrelated remote origin invokes a desktop command
- **WHEN** content outside the exact HTTP `127.0.0.1` origin pattern invokes a custom desktop command
- **THEN** Tauri does not grant access through the loopback capability

### Requirement: Loopback permissions remain least privilege
The loopback capability SHALL grant only the seven application commands and supporting event/external-link access required by the GUI; it SHALL NOT grant process restart or sidecar spawn permissions.

#### Scenario: Capability contract is inspected
- **WHEN** packaging tests inspect the loopback capability and Tauri app manifest
- **THEN** all seven registered application commands are present and broad process/spawn permissions are absent
