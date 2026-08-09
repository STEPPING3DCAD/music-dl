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

### Requirement: Reconnect repairs valid legacy credentials
The system SHALL rewrite saved Tidal credentials through the corrected serializer when reconnect discovers that the current remote session is still valid.

#### Scenario: Shifted local expiry but valid remote session
- **WHEN** Re-connect checks a session that remains valid remotely but was saved with an early timezone-shifted expiry
- **THEN** the system SHALL re-persist the session and return `already_logged_in` so local status no longer reports the repaired token as expired

#### Scenario: Remote session is invalid
- **WHEN** Re-connect checks credentials that are invalid remotely
- **THEN** the system SHALL continue into the existing OAuth device-login flow instead of treating them as repaired
