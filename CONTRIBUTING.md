# Contributing

This started as a single-operator project, so the workflow is lightweight.

## Reporting an issue

Use the issue templates. Include your Pi model, Python version, and the exact
command that failed if it's a firmware issue.

## Proposing a change

1. Fork the repo and create a branch from `main`.
2. Run `make test` before opening a PR. CI runs the same suite.
3. Keep firmware changes hardware-agnostic where possible, test with `--mock` first.
4. For ML changes, include the updated metrics table from `ml/*/reports/`.

## Code style

- Python: standard library formatting, type hints on public functions.
- JS/React: whatever `npm run lint` in `backend/` and `dashboard/` enforces.

## Development without hardware

You do not need a Raspberry Pi or an Azure subscription to contribute to
firmware logic or the dashboard. See the Quickstart in the main README for
mock mode and `docker-compose up`.
