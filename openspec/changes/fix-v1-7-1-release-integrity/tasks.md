# v1.7.1 Release Integrity Implementation Plan

> **For agentic workers:** Use Superpowers TDD, execution, verification, and branch-finishing discipline. Do not tag or publish binaries until this change is merged and both platform updater flows pass.

**Goal:** Restore trusted desktop update access and make local library metadata and quality internally consistent.

**Architecture:** Extend existing boundaries only: Tauri capability files own desktop access, the scanner owns resolved local facts, the library database persists them, and the existing JavaScript quality helper renders them.

**Tech Stack:** Python, SQLite, vanilla JavaScript, Tauri 2/Rust, pytest, Bun tests, OpenSpec.

## 1. Restore loopback desktop access

- [x] 1.1 Add a failing packaging contract for the exact loopback origin, seven custom commands, and least-privilege permission set.
- [x] 1.2 Register the seven commands in the Tauri app manifest and add the dedicated loopback capability.
- [x] 1.3 Run the focused packaging contract and Rust configuration/build checks.

## 2. Make codec the local quality authority

- [x] 2.1 Add failing scanner/database and JavaScript tests for AAC-in-M4A, ALAC-in-M4A, and unknown codec.
- [x] 2.2 Persist normalized codec through schema migration, scans, and API serialization.
- [x] 2.3 Pass `(quality, format, codec)` to every local quality classification and ranking call.

## 3. Resolve incomplete local metadata once

- [x] 3.1 Add failing tests for embedded-tag precedence, generic-title fallback, missing-artist folder inference, and ambiguous shallow paths.
- [x] 3.2 Add the pure scan-time resolver and use it for new and legacy incomplete rows.
- [x] 3.3 Verify source audio remains unchanged and inferred rows do not repeat repair work.

## 4. Verify and document

- [x] 4.1 Update relevant local-library/backend documentation.
- [x] 4.2 Run focused tests, full fast-feedback gates, strict OpenSpec validation, and Ponytail diff review.
- [ ] 4.3 Merge only with required checks green; then build binaries and test real update flow on macOS and Windows PLEX-MINI.
