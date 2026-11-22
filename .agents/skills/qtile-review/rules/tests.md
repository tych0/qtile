# Tests

## 15. Tests for behaviour changes

Bug fixes need a regression test that fails without the fix. New features need
tests. Behaviour that involves the window manager should be tested through the
`manager` fixture (`test/conftest.py`), which runs on both backends; a test
limited to one backend must say why.

## 16. No sleeps in tests

Flag `time.sleep` in tests used to wait for something to happen. Suggest the
`Retry` helper in `test/helpers.py` to poll for the condition instead.
