# User-visible API and config compatibility

Users' configs are Python files that import from `libqtile`. Anything a config
can name or rely on is user-visible API.

## 5. Migrate user-visible API changes

Renaming or removing a config option, widget parameter or class, command, hook
name, layout argument, or `lazy` call needs a migration in
`libqtile/scripts/migrations/` so `qtile migrate` can update users' configs.
The migration must include `TESTS` covering the change. See
`docs/manual/how-to-migrate.rst`.

Where practical, also keep a deprecation shim that logs a warning for a
release cycle.

## 6. Changelog entry

User-visible changes (new features, behaviour changes, removals) need an entry
in `CHANGELOG` under the unreleased version, in the `features` or `bugfixes`
list. Breaking changes need an entry under `!!! Breaking changes !!!`.

## 7. Don't change defaults quietly

Changing a default value is a user-visible change, so rules 5 and 6 apply even
though no signature changed. The commit message should say why.

## 8. Command surface

New or changed `@expose_command` methods need docstrings, since those become
the command documentation. Arguments must survive the IPC/CLI boundary (no
non-serialisable types). Removing or renaming a command is a breaking change.
