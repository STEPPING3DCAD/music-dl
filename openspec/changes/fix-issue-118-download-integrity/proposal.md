## Why

Desktop downloads can return an explicit failed outcome without raising, but the GUI job worker currently records the job as done and emits a completion event anyway. This violates the documented no-silent-failure contract and matches issue #118: the queue advances rapidly while no destination folders or files appear.

## What Changes

- Make GUI download terminal state follow the existing `DownloadOutcome` returned by `Download.item()`.
- Record and broadcast an error when a standard GUI download returns `FAILED`; do not create success history or emit `complete`.
- Preserve terminal success for the existing `DOWNLOADED`, `COPIED`, and `SKIPPED` outcomes.
- Add focused regression coverage for failed and successful GUI worker outcomes, then document the outcome gate in the backend flow.

## Capabilities

### New Capabilities

- `gui-download-terminal-integrity`: GUI download jobs report completion only when the download layer returns a terminal success outcome.

### Modified Capabilities

None.

## Impact

The implementation is limited to the existing GUI download worker, its focused pytest coverage, and the backend download-pipeline documentation. No public API shape, database schema, dependency, source-selection policy, retry policy, CLI behavior, or frontend module changes.
