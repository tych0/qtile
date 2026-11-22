# Dependencies

Also apply the dependency section of rule 1 in `concurrency.md` to every new
dependency.

## 11. No new hard dependencies

A new third-party import used by a widget or other optional feature must be
imported lazily (inside the function or `_configure`) or guarded, must be
documented in the widget's or feature's docstring, and must fail gracefully
with a clear message when it's missing. Flag anything that adds to qtile's core
install requirements in `pyproject.toml`; that needs a strong justification.

## 12. Shelling out

Prefer Python libraries, or existing qtile helpers, to calling external
binaries. If a binary is needed, its name or path should be configurable and
documented, and it must be called asynchronously (rule 2).
