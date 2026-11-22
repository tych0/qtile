---
name: qtile-review
description: Review a qtile diff or pull request against qtile's project policies (no new threads, migrations for user-visible API changes, backend parity, new dependencies, resource leaks in C/cffi code). Use when asked to review qtile changes.
---

# qtile review

Review a change against qtile's project policies. The rules live in `rules/`;
paths below are relative to this file's directory.

## Workflow

1. Get the diff to review: the PR's diff, or `git diff master...HEAD` for a
   local branch. Also read the commit messages.
2. Pick the rule files that apply, based on what the diff touches:
   - any Python change: `rules/concurrency.md`, `rules/conventions.md`,
     `rules/tests.md`
   - config options, commands, hooks, layout or widget parameters, defaults,
     or anything else a user's config can see: `rules/api-compat.md`,
     `rules/docs.md`
   - `libqtile/backend/`, `libqtile/core/`, or code that branches on the
     backend: `rules/backends.md`
   - new imports of third-party packages, or changes to `pyproject.toml`:
     `rules/dependencies.md`, and the dependency section of
     `rules/concurrency.md`
   - `libqtile/widget/`: `rules/widgets.md`
   - `.c`/`.h` files (e.g. `libqtile/backend/wayland/qw/`), the cffi build
     (`libqtile/backend/wayland/cffi/`), or Python code calling into `ffi`/`lib`:
     `rules/native-resources.md`
3. Read only those rule files, then check the diff against each rule in them.
   Read surrounding code where needed to judge a rule; don't judge from the
   diff hunk alone.
4. Write the report (format below).

Rules may be checked independently of each other, so a harness that can run
reviews in parallel may split the work by rule file.

## Report format

For each finding:

- **Rule:** number and short name (e.g. `1 No new threads`)
- **Location:** `path/to/file.py:123`
- **Problem:** what is wrong, in one or two sentences
- **Fix:** the suggested change

Order findings by severity: crashes, leaks and breaking changes first, style
last. Include the per-dependency table (rule 1) and the per-acquisition table
(rule 23) whenever those rules apply.

If a rule can't be checked from the information available (for example,
a dependency's source can't be fetched), say so as an open question for the
author rather than passing or failing it.

If nothing violates a rule, say so plainly. Don't invent findings to have
something to report.
