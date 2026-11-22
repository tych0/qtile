# Widgets

## 13. Widget conventions

- Use the base classes in `libqtile/widget/base.py` (`BackgroundPoll`,
  `InLoopPollText`, etc.). Widgets must not add their own polling loops, timers
  or exception handling that the base classes already provide (see
  `docs/manual/contributing.rst`).
- Configuration goes in `defaults`, with a description for each entry.
  Don't hardcode colours or fonts.
- Polling intervals under about one second need a stated reason.
- Mouse callbacks follow the existing naming and use `add_callbacks`.

## 14. Widget documentation

New widgets need a class docstring explaining what they show and any
requirements (external packages or binaries), and must be exported so they
appear in the generated widget docs.
