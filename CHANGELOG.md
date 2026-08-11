# Changelog

All notable changes to Research Analyst are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); this project uses [Semantic Versioning](https://semver.org/).
Releases are cut by tagging the repo (see `docs/VERSIONING.md`); GitHub auto-generates the per-release notes from merged PRs.

## [Unreleased]

## [0.2.2] - 2026-08-11
### Added
- Standardized version automation: a single-source version bump (`scripts/bump-version.mjs`) propagates one version across `package.json`, the on-page footer, the PWA manifest, and the service-worker cache; CI stamps Android `versionName`/`versionCode` (and iOS `CFBundleShortVersionString`/`CFBundleVersion` when present) from the release tag (`scripts/stamp-app-version.sh`). Full standard in `docs/VERSIONING.md`.
- Fluid, resolution-aware UI sizing and crisper responsive Plotly charts + Mermaid diagrams (PR #20).

## [0.2.1]
Baseline: institutional research UI (single + comparative modes), Markdown/HTML/PDF export, installable offline-capable PWA, Android APK (Capacitor WebView), and the aimlds.org mirror.
