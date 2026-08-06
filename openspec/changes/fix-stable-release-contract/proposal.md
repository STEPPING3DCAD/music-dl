## Why

The v1.7.1 release preflight is blocked by a stale shell assertion that searches the desktop workflow for an inline UTF-8 file read removed when static-asset verification moved into the shared pytest suite. The workflow and shared reader retain the intended protection, but the contract test no longer follows that boundary.

## What Changes

- Verify that the stable desktop workflow invokes the shared static-asset test suite.
- Verify that the shared GUI JavaScript reader explicitly uses UTF-8.
- Leave production code, build behavior, dependencies, and release metadata unchanged.

## Capabilities

### New Capabilities

- `stable-release-contract`: Release preflight follows the shared static-asset verification seam and preserves explicit UTF-8 decoding.

### Modified Capabilities

None.

## Impact

Only `tests/test_stable_release_workflow.sh` and this OpenSpec change are modified. The repair unblocks the existing v1.7.1 release workflow without changing generated binaries.
