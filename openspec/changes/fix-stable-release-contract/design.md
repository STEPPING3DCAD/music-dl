## Context

Commit `37e6bf9` replaced duplicated Linux and Windows inline JavaScript reads in `build-desktop.yml` with `pytest tests/test_static_assets.py`. That suite uses `tests.gui_js_source.read_gui_js`, whose only file-read implementation already specifies UTF-8. `tests/test_stable_release_workflow.sh` still expects the removed inline source text and now fails before tagging v1.7.1.

## Decision

Extend the existing shell contract to inspect the durable seams: the workflow must invoke `tests/test_static_assets.py`, and `tidaldl-py/tests/gui_js_source.py` must contain the explicit UTF-8 read. Do not restore an inline workflow script or add another helper.

This cannot be simpler without dropping regression coverage. Reusing the existing shared reader adds no abstraction or runtime complexity; duplicating the read in YAML would create two verification implementations that can drift again.

## Risks / Trade-offs

- [The helper path changes] -> The contract fails and forces the workflow/test boundary to be updated together.
- [UTF-8 decoding becomes implicit] -> The contract fails before a Windows runner can use a different default encoding.

## Migration Plan

Merge the test-only repair, rerun release preflight, then tag the unchanged v1.7.1 merge commit and let `build-desktop.yml` publish signed updater artifacts.
