<!--
Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com> — SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# Contributing to Research Analyst

Thank you for your interest in contributing. This document outlines the standards and process.

---

## Code Standards

### Python

- **Python 3.11+** required
- **Type hints** on all public functions and method signatures
- **Docstrings** on all public classes and functions (Google style)
- **Pydantic v2** for all data models (no raw dicts in the data pipeline)
- **ruff** for linting and formatting (config in `pyproject.toml`)
- **mypy** for type checking (strict mode)
- Line length: 100 characters

### JavaScript

- Vanilla JS only (no frameworks, no build step)
- All DOM manipulation via `textContent` or controlled `innerHTML` (XSS prevention)
- No `eval()`, no `new Function()`, no inline event handlers in HTML

### CSS

- CSS custom properties for theming
- No CSS frameworks
- Mobile-first responsive design

### General

- Every external API call must have: timeout, retry with backoff, error handling
- Every computed metric must trace to an explicit assumption
- No silent failures: log warnings for missing data, return typed defaults
- O(n) or O(n log n) algorithms preferred; O(n^2) requires justification in comments

---

## Development Setup

```bash
git clone https://github.com/nrupala/research-analyst.git
cd research-analyst
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Running Checks

```bash
# Lint
ruff check .

# Format
ruff format .

# Type check
mypy research_analyst/ --ignore-missing-imports

# Tests
pytest --cov=research_analyst
```

---

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Write code following the standards above
4. Add tests for new functionality
5. Run all checks (lint, typecheck, test) — all must pass
6. Submit a PR with a clear description of what changed and why

### PR Checklist

- [ ] Code follows the standards above
- [ ] Type hints on all new public functions
- [ ] Docstrings on all new public classes/functions
- [ ] Tests added/updated
- [ ] `ruff check .` passes
- [ ] `mypy research_analyst/` passes
- [ ] `pytest` passes
- [ ] No PAE, no Aladdin, no unrelated project references in code or docs

---

## Architecture Rules

1. **Models in `models.py`** — all data structures live in one file, typed with Pydantic
2. **Providers fetch** — they talk to external APIs and return typed models
3. **Engines analyze** — they take typed models in, produce typed analysis out
4. **Renderer assembles** — it takes analysis + templates and produces reports
5. **Orchestrator coordinates** — it ties providers, engines, and renderer together
6. **Server exposes** — it wraps the orchestrator in an HTTP API

Do not bypass this layering. No engine should call an external API directly. No provider should analyze data.

---

## License

By contributing, you agree that your contributions will be licensed under the AGPL-3.0 license.
