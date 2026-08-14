## ADDED Requirements

### Requirement: GUI terminal state follows download outcome
The GUI download worker SHALL derive terminal job state from the `DownloadOutcome` returned by `Download.item()` rather than from the absence of an exception.

#### Scenario: Download layer reports failure
- **WHEN** a claimed standard GUI download returns `DownloadOutcome.FAILED`
- **THEN** the worker records error history, marks the job as error, and broadcasts an error event without recording done history or broadcasting completion

#### Scenario: Download layer reports a terminal success
- **WHEN** a claimed standard GUI download returns `DownloadOutcome.DOWNLOADED`, `DownloadOutcome.COPIED`, or `DownloadOutcome.SKIPPED`
- **THEN** the worker records done history, marks the job done with 100 percent progress, and broadcasts completion

### Requirement: Failed GUI downloads remain observable
The GUI download worker MUST preserve existing error persistence and SSE behavior for a returned failed outcome so the desktop client cannot display a false green completion.

#### Scenario: Failure does not create output
- **WHEN** the download layer returns `DownloadOutcome.FAILED` with no output path or destination directory
- **THEN** the persisted job and emitted event report failure and no success state is created

#### Scenario: Error-history persistence also fails
- **WHEN** the worker handles a returned failed outcome and error-history persistence raises
- **THEN** the worker still marks the job as error and broadcasts the error event through the existing guarded error path
