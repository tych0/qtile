import copy
from typing import Any

from libqtile.log_utils import logger


class Configurable:
    global_defaults = {}  # type: dict

    def __init__(self, **config):
        self._variable_defaults = {}
        self._validators = {}
        self._user_config = config

    def add_defaults(self, defaults):
        """Add defaults to this object, overwriting any which already exist

        Defaults can be tuples of (name, value, description) or
        (name, value, description, validator_func) where validator_func
        takes a value and raises ValueError if invalid.
        """
        # Since we can't check for immutability reliably, shallow copy the
        # value. If a mutable value were set and it were changed in one place
        # it would affect all other instances, since this is typically called
        # on __init__
        for d in defaults:
            name, value = d[0], d[1]
            self._variable_defaults[name] = copy.copy(value)
            # If there's a 4th element, it's a validator function
            if len(d) >= 4 and d[3] is not None:
                self._validators[name] = d[3]

    def __getattr__(self, name):
        if name in ("_variable_defaults", "_user_config", "_validators"):
            raise AttributeError
        found, value = self._find_default(name)
        if found:
            setattr(self, name, value)
            return value
        else:
            cname = self.__class__.__name__
            raise AttributeError(f"{cname} has no attribute: {name}")

    def _find_default(self, name) -> tuple[bool, Any]:
        """Returns a tuple (found, value)"""
        if name in self._user_config:
            return True, self._user_config[name]

        if name in self.global_defaults:
            return True, self.global_defaults[name]

        if name in self._variable_defaults:
            return True, self._variable_defaults[name]

        return False, None

    def validate(self) -> None:
        valid_keys = set(self.global_defaults.keys()) | set(self._variable_defaults.keys())
        invalid_keys = set(self._user_config.keys()) - valid_keys
        if invalid_keys:
            cname = self.__class__.__name__
            raise AttributeError(
                f"{cname} has no configuration parameter(s): {', '.join(sorted(invalid_keys))}"
            )

        # Validate user-supplied values using validator functions if present
        cname = self.__class__.__name__
        for param_name, param_value in self._user_config.items():
            if param_name in self._validators:
                validator = self._validators[param_name]
                try:
                    validator(param_value)
                except ValueError as e:
                    logger.error(
                        f"{cname}: parameter '{param_name}' has invalid value {param_value!r}: {e}"
                    )


class ExtraFallback:
    """Adds another layer of fallback to attributes

    Used to look up a different attribute name
    """

    def __init__(self, name, fallback):
        self.name = name
        self.hidden_attribute = "_" + name
        self.fallback = fallback

    def __get__(self, instance, owner=None):
        retval = getattr(instance, self.hidden_attribute, None)

        if retval is None:
            _found, retval = Configurable._find_default(instance, self.name)

        if retval is None:
            retval = getattr(instance, self.fallback, None)

        return retval

    def __set__(self, instance, value):
        """Set own value to a hidden attribute of the object"""
        setattr(instance, self.hidden_attribute, value)
