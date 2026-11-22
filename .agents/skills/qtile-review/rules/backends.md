# Backend parity

## 9. X11 and Wayland parity

New core features should work on both backends. If one backend can't support a
feature, the PR must document the limitation, fail clearly on that backend
(log a warning or raise a clear error, not silently do nothing), and skip the
relevant tests explicitly with a reason.

## 10. No backend leaks

Generic code (layouts, widgets, `libqtile/core/`, config handling) must not
import from `libqtile.backend.x11` or `libqtile.backend.wayland`, or branch on
`qtile.core.name`, unless there is no alternative. Suggest adding a method to
the backend interface in `libqtile/backend/base/` instead.
