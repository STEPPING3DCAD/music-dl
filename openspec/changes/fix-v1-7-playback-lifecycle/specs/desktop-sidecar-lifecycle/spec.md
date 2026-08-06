## ADDED Requirements

### Requirement: Owned sidecar process tree is terminated
The desktop app SHALL terminate all descendants of an app-owned packaged sidecar before terminating the wrapper process on Unix, and SHALL retain whole-tree termination on Windows.

#### Scenario: macOS wrapper owns a daemon child
- **WHEN** the app quits, restarts the sidecar, abandons a failed launch, or installs an update
- **THEN** the daemon child and wrapper exit and the listening port is released

#### Scenario: Descendant exits during cleanup
- **WHEN** a discovered descendant exits before it is signaled
- **THEN** cleanup continues and still attempts to terminate the wrapper

#### Scenario: App shares a process group
- **WHEN** the sidecar and app are members of the same process group
- **THEN** cleanup targets only the wrapper's descendant tree and does not signal the process group

### Requirement: Updater reuses lifecycle cleanup
The updater SHALL use the same owned-sidecar cleanup function as normal lifecycle shutdown.

#### Scenario: Update installation begins
- **WHEN** an update is staged and an app-owned sidecar exists
- **THEN** updater cleanup removes its descendants before installation proceeds
