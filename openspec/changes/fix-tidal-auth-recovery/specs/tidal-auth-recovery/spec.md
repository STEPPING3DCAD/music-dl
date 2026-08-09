## ADDED Requirements

### Requirement: Desktop reset confirmation
The system SHALL require an in-app confirmation that works in browser and packaged desktop modes before deleting saved Tidal credentials.

#### Scenario: User continues reset
- **WHEN** a user activates Reset Tidal connection and chooses Continue in the in-app confirmation
- **THEN** the system sends one reset request, refreshes both authentication status surfaces, and reports success

#### Scenario: User cancels reset
- **WHEN** a user cancels, presses Escape, or dismisses the in-app confirmation
- **THEN** the system SHALL NOT send a reset request or alter saved credentials

### Requirement: Timezone-safe token expiry
The system SHALL persist a naive expiry datetime returned by the Tidal client as UTC rather than interpreting it in the device's local timezone.

#### Scenario: OAuth completes outside UTC
- **WHEN** Tidal returns a naive UTC expiry on a device whose local timezone differs from UTC
- **THEN** the stored epoch SHALL represent the same UTC instant without applying the local timezone offset

#### Scenario: Tidal returns an aware expiry
- **WHEN** Tidal returns a timezone-aware expiry datetime
- **THEN** the stored epoch SHALL preserve that represented instant

#### Scenario: Correct stored epoch is reloaded
- **WHEN** an existing numeric expiry epoch is loaded and persisted again during reconnect
- **THEN** the stored epoch SHALL remain unchanged regardless of the device's local timezone

### Requirement: Reconnect repairs valid legacy credentials
The system SHALL rewrite saved Tidal credentials through the corrected serializer when reconnect discovers that the current remote session is still valid.

#### Scenario: Shifted local expiry but valid remote session
- **WHEN** Re-connect checks a session that remains valid remotely but was saved with an early timezone-shifted expiry
- **THEN** the system SHALL refresh and persist the session with a fresh provider expiry before returning `already_logged_in` so local status no longer reports the repaired token as expired

#### Scenario: Remote session is invalid
- **WHEN** Re-connect checks credentials that are invalid remotely
- **THEN** the system SHALL continue into the existing OAuth device-login flow instead of treating them as repaired

#### Scenario: Valid session cannot be refreshed
- **WHEN** Re-connect validates the remote session but its refresh token is missing, rejected, or fails
- **THEN** the system SHALL continue into the existing OAuth device-login flow instead of returning `already_logged_in`

### Requirement: Published hotfix update discovery
The system SHALL publish the repair as stable v1.7.2 through the existing signed desktop updater pipeline.

#### Scenario: Stable release artifacts are complete
- **WHEN** the merged hotfix is tagged `v1.7.2`
- **THEN** the release SHALL contain signed updater artifacts for macOS, Linux, and Windows plus a `latest.json` manifest that advertises version `1.7.2`

#### Scenario: Existing app discovers the hotfix
- **WHEN** an installed v1.7.1 app checks the stable updater endpoint after v1.7.2 is published
- **THEN** the app SHALL show that version `1.7.2` is available
