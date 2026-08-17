# Repository Guidelines

## Project Structure & Module Organization

`projects/docs-and-handbooks/` is the source of truth for Wiki Markdown, images, and attachments. Its collections include `awesome_handbook/`, `learning_guide/`, `books/`, and the archived `survive_scu_manual/`. The Python generator lives in `tools/build_handbook_wiki.py`; `tools/build_docs_site.py` is a compatibility entry point. Generated, deployable output belongs in `docs-site/`, including mirrored content, indexes, the manifest, link-audit data, and browser assets. Do not edit generated files alone: change the source document or generator template, then rebuild. GitHub Pages deployment is defined in `.github/workflows/deploy-pages.yml`.

## Build, Test, and Development Commands

- `python3 tools/build_handbook_wiki.py` rebuilds `docs-site/` using only the Python standard library.
- `python3 tools/build_handbook_wiki.py --check-external` also audits public external links; it requires network access and may be slower.
- `python3 -m http.server 4173 -d docs-site` serves the generated site at `http://127.0.0.1:4173/` for local review.

No dependency-install step or separate compilation command is required.

## Coding Style & Naming Conventions

Use four-space indentation in Python, `snake_case` for functions and variables, `PascalCase` for dataclasses, and `UPPER_SNAKE_CASE` for constants. Retain modern type hints and the existing import grouping. Embedded JavaScript uses two spaces, `camelCase`, semicolons, and `const` by default; CSS classes and custom properties use kebab-case. Markdown should be UTF-8, start with a clear ATX heading, use fenced code blocks, and prefer relative links. Preserve established Chinese and historical filenames; new topic files should use descriptive kebab-case where practical. No formatter or linter is configured, so match nearby code.

## Testing Guidelines

There is no automated test suite or coverage threshold. Treat a clean generator run as the smoke test, then preview the site and inspect navigation, Markdown rendering, local links, and assets. Run the external-link check for link-heavy changes. Review the resulting `docs-site/` diff and avoid committing unrelated generated churn.

## Commit & Pull Request Guidelines

History is short, so conventions are limited. Use concise, action-oriented subjects; prefixes such as `docs:`, `fix:`, or `build:` match the existing `fix:` style. Pull requests should explain the motivation, identify changed source collections, link relevant issues, and state validation performed. Include regenerated output, screenshots for UI or rendering changes, and explicit notes about new large or binary attachments.

## Security & Publication Checks

Before public deployment, review historical installers and archives, internal domains, stale URLs, and attachments for sensitive or inappropriate material. Never add credentials or private configuration.
