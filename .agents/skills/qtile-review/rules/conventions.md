# Code quality and conventions

## 17. Logging and exceptions

Use `libqtile.log_utils.logger`, never `print`. Normal operation should not log
at warning level or above. Exceptions caught in hooks, commands or widgets must
be logged (`logger.exception`), not swallowed with a bare `except:` or
`except Exception: pass`.

## 18. Type hints

New public functions and methods need type annotations. Don't add
`# type: ignore` without a comment saying why.

## 19. Hooks

New hooks need a docstring (it ends up in the docs) and must fire on both
backends. Changing the arguments of an existing hook is a breaking change, so
rules 5 and 6 apply.

## 20. Config safety

Changes to config loading or reloading must not crash on an old or invalid user
config: qtile should fall back to the default config and report the error.
`qtile check` must keep working.

## 21. Scope and commits

Flag unrelated reformatting, quote or whitespace changes, drive-by linter
fixes on untouched code, and refactors the change doesn't need; suggest a
separate PR. Each commit should make sense and pass CI on its own, and must not
introduce code that a later commit in the same PR rewrites. Commit messages
should carry the relevant detail (stack traces, links to specs or issues).
