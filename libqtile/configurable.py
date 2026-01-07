import copy
from typing import Any


class Configurable:
    global_defaults = {}  # type: dict

    def __init__(self, **config):
        self._variable_defaults = {}
        self._user_config = config

    def add_defaults(self, defaults):
        """Add defaults to this object, overwriting any which already exist"""
        # Since we can't check for immutability reliably, shallow copy the
        # value. If a mutable value were set and it were changed in one place
        # it would affect all other instances, since this is typically called
        # on __init__
        self._variable_defaults.update((d[0], copy.copy(d[1])) for d in defaults)

    def __getattr__(self, name):
        if name in ("_variable_defaults", "_user_config"):
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
