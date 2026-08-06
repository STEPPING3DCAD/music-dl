# Stable Release Contract Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: follow Superpowers TDD, execution, verification, and branch-finishing discipline. Do not tag until this change is merged and all release preflight gates pass.

**Goal:** Make the stable-release contract follow the shared static-asset verification seam without changing binary behavior.

**Architecture:** Modify only the existing shell contract. Reuse `tests/test_static_assets.py` as the workflow boundary and `tests.gui_js_source.read_gui_js` as the UTF-8 boundary.

**Tech Stack:** Bash contract tests, Python/pytest shared helper, GitHub Actions, OpenSpec.

## 1. Align the release contract

- [x] 1.1 Run `bash tests/test_stable_release_workflow.sh` on merged v1.7.1 and record RED: failure at `stable workflow reads static assets as UTF-8` because the removed inline `read_text(encoding='utf-8')` string is absent.
- [x] 1.2 Update `tests/test_stable_release_workflow.sh` to read `tidaldl-py/tests/gui_js_source.py`, require the workflow to invoke `tests/test_static_assets.py`, and require the shared helper to contain `read_text(encoding="utf-8")`.
- [x] 1.3 Rerun `bash tests/test_stable_release_workflow.sh`, the macOS/Windows installer contracts, focused updater/static tests, release metadata check, and strict OpenSpec validation.
- [x] 1.4 Perform Ponytail review and confirm no production or workflow files changed.
