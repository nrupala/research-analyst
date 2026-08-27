# Changelog

All notable changes to Research Analyst are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); this project uses [Semantic Versioning](https://semver.org/).
Releases are cut by tagging the repo (see `docs/VERSIONING.md`); GitHub auto-generates the per-release notes from merged PRs.

## [Unreleased]

## [0.3.0] - 2026-08-27
### Added
- First-use disclaimer acknowledgment gate in the UI: on first load fetches `GET /api/disclaimer` and shows the full disclaimer; acknowledgment persists in `localStorage` (`ra_disclaimer_ack`) per version. Fail-open on error, fail-safe `hidden` baseline. (PR #35)
- `GET /api/disclaimer` endpoint returning `{version, full, short}`. (PR #34)
- India ticker resolver: curated NSE alias map resolved first (e.g. `ICICI -> ICICIBANK.NS`) plus a safe "did you mean `X.NS`?" suggestion for bare, suffix-less symbols that return no search match. (PR #34)
### Fixed
- Report disclaimers unified to a single source of truth (`research_analyst/disclaimer.py`); generic, non-jurisdiction copy across text/markdown/HTML. (PR #34)
- Markdown reports rendered a `**Disclaimer:**` header with an empty body; the body now renders from the single source. (PR #34)
### CI
- Headless UI tests now gate on `ubuntu-latest`: `ui/tests/compare.test.mjs` and the new `ui/tests/disclaimer_gate.test.mjs`.

## [0.2.2] - 2026-08-11
### Added
- Standardized version automation: a single-source version bump (`scripts/bump-version.mjs`) propagates one version across `package.json`, the on-page footer, the PWA manifest, and the service-worker cache; CI stamps Android `versionName`/`versionCode` (and iOS `CFBundleShortVersionString`/`CFBundleVersion` when present) from the release tag (`scripts/stamp-app-version.sh`). Full standard in `docs/VERSIONING.md`.
- Fluid, resolution-aware UI sizing and crisper responsive Plotly charts + Mermaid diagrams (PR #20).

## [0.2.1]
Baseline: institutional research UI (single + comparative modes), Markdown/HTML/PDF export, installable offline-capable PWA, Android APK (Capacitor WebView), and the aimlds.org mirror.
