## ADDED Requirements

### Requirement: Tests use temporary configuration
The pytest suite SHALL set a session-temporary configuration directory before application imports and test-module collection, then use a per-test temporary configuration directory and reset configuration singletons around each test by default.

#### Scenario: Test module is collected
- **WHEN** pytest imports a test module that imports application configuration
- **THEN** `MUSIC_DL_CONFIG_DIR` already points outside the user's real configuration

#### Scenario: Test creates the GUI app
- **WHEN** a test starts application lifespan without configuring paths
- **THEN** it cannot inherit or scan the developer's real music folders

#### Scenario: Test overrides configuration
- **WHEN** a test explicitly sets its own configuration directory or settings
- **THEN** that test remains isolated within its temporary test scope

### Requirement: Full suite is safe to execute
The release gate SHALL include a complete pytest run after the isolation fixture is active.

#### Scenario: Full suite runs on a configured developer machine
- **WHEN** the developer has real NAS paths in the normal application config
- **THEN** tests complete without accessing those paths or leaving a background scan
