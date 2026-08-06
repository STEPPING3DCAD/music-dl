## ADDED Requirements

### Requirement: Stable desktop workflow uses shared static-asset verification
The stable desktop release workflow SHALL run the shared static-asset test suite, and the shared GUI JavaScript reader SHALL decode source files explicitly as UTF-8.

#### Scenario: Release preflight inspects the workflow
- **WHEN** the stable-release contract test runs
- **THEN** it confirms `build-desktop.yml` invokes `tests/test_static_assets.py`

#### Scenario: Shared GUI sources are read on Windows
- **WHEN** the static-asset suite combines split GUI JavaScript files
- **THEN** the shared reader uses explicit UTF-8 decoding rather than the platform default
