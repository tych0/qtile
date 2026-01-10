from libqtile import configurable


class ConfigurableWithFallback(configurable.Configurable):
    defaults = [
        ("foo", 3, ""),
    ]

    bar = configurable.ExtraFallback("bar", "foo")

    def __init__(self, **config):
        configurable.Configurable.__init__(self, **config)
        self.add_defaults(ConfigurableWithFallback.defaults)


def test_use_fallback():
    c = ConfigurableWithFallback()
    assert c.foo == c.bar == 3

    c = ConfigurableWithFallback(foo=5)
    assert c.foo == c.bar == 5


def test_use_fallback_if_set_to_none():
    # Even if it is explicitly set to None, we should still
    # use the fallback. Could be useful if widget_defaults
    # were to set bar= and we wanted to specify that an
    # individual widget should fall back to using foo.
    c = ConfigurableWithFallback(foo=7, bar=None)
    assert c.foo == c.bar == 7

    c = ConfigurableWithFallback(foo=9)
    c.bar = None
    assert c.foo == c.bar == 9


def test_dont_use_fallback_if_set():
    c = ConfigurableWithFallback(bar=5)
    assert c.foo == 3
    assert c.bar == 5

    c = ConfigurableWithFallback(bar=0)
    assert c.foo == 3
    assert c.bar == 0

    c = ConfigurableWithFallback(foo=1, bar=2)
    assert c.foo == 1
    assert c.bar == 2

    c = ConfigurableWithFallback(foo=1)
    c.bar = 3
    assert c.foo == 1
    assert c.bar == 3


def test_validate_valid_config():
    c = ConfigurableWithFallback(foo=5)
    c.validate()  # Should not raise


def test_validate_invalid_config():
    import pytest

    c = ConfigurableWithFallback(invalid_key=10)
    with pytest.raises(
        AttributeError, match="ConfigurableWithFallback has no configuration parameter"
    ):
        c.validate()


def test_validate_multiple_invalid_keys():
    import pytest

    c = ConfigurableWithFallback(invalid1=1, invalid2=2)
    with pytest.raises(AttributeError, match="invalid1.*invalid2"):
        c.validate()


def test_validator_function_valid():
    """Test that validator functions are called with valid values"""

    def validate_positive(value):
        if value <= 0:
            raise ValueError("Value must be positive")

    class ConfigWithValidator(configurable.Configurable):
        defaults = [
            ("count", 5, "A positive number", validate_positive),
        ]

        def __init__(self, **config):
            configurable.Configurable.__init__(self, **config)
            self.add_defaults(ConfigWithValidator.defaults)

    # Valid value should not raise
    c = ConfigWithValidator(count=10)
    c.validate()  # Should not raise or log errors


def test_validator_function_invalid(caplog):
    """Test that validator functions log errors for invalid values"""

    def validate_positive(value):
        if value <= 0:
            raise ValueError("Value must be positive")

    class ConfigWithValidator(configurable.Configurable):
        defaults = [
            ("count", 5, "A positive number", validate_positive),
        ]

        def __init__(self, **config):
            configurable.Configurable.__init__(self, **config)
            self.add_defaults(ConfigWithValidator.defaults)

    c = ConfigWithValidator(count=-5)
    c.validate()

    # Check that error was logged
    assert len(caplog.records) == 1
    log_record = caplog.records[0]
    assert log_record.levelname == "ERROR"
    assert "ConfigWithValidator" in log_record.message
    assert "count" in log_record.message
    assert "-5" in log_record.message
    assert "Value must be positive" in log_record.message


def test_validator_function_none():
    """Test that None as validator is handled correctly"""

    class ConfigWithNoneValidator(configurable.Configurable):
        defaults = [
            ("foo", 5, "A parameter", None),  # Explicit None validator
            ("bar", 10, "Another parameter"),  # No validator (3-tuple)
        ]

        def __init__(self, **config):
            configurable.Configurable.__init__(self, **config)
            self.add_defaults(ConfigWithNoneValidator.defaults)

    # Should not raise errors with any values since no validators
    c = ConfigWithNoneValidator(foo=-100, bar=-200)
    c.validate()  # Should not raise or log errors


def test_validator_function_multiple_params(caplog):
    """Test validators on multiple parameters"""

    def validate_positive(value):
        if value <= 0:
            raise ValueError("Must be positive")

    def validate_range(value):
        if not 0 <= value <= 100:
            raise ValueError("Must be between 0 and 100")

    class ConfigMultiValidator(configurable.Configurable):
        defaults = [
            ("width", 10, "Width", validate_positive),
            ("height", 20, "Height", validate_positive),
            ("opacity", 50, "Opacity percentage", validate_range),
        ]

        def __init__(self, **config):
            configurable.Configurable.__init__(self, **config)
            self.add_defaults(ConfigMultiValidator.defaults)

    # Multiple invalid values
    c = ConfigMultiValidator(width=-5, opacity=150)
    c.validate()

    # Should have 2 error logs
    assert len(caplog.records) == 2
    messages = [r.message for r in caplog.records]

    # Check both errors are present
    assert any("width" in msg and "-5" in msg and "Must be positive" in msg for msg in messages)
    assert any(
        "opacity" in msg and "150" in msg and "Must be between 0 and 100" in msg
        for msg in messages
    )
