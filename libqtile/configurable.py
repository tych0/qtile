import copy


class Configurable:
    global_defaults = {}  # type: dict

    def __init__(self, **config):
        self._variable_defaults = {}
        self._user_config = config
        # Set user config values as instance attributes, but skip read-only properties
        for name, value in config.items():
            class_attr = getattr(type(self), name, None)
            if isinstance(class_attr, property) and class_attr.fset is None:
                continue  # Skip read-only properties, value stays in _user_config
            setattr(self, name, value)

    def add_defaults(self, defaults):
        """Add defaults to this object, overwriting any which already exist"""
        # Since we can't check for immutability reliably, shallow copy the
        # value. If a mutable value were set and it were changed in one place
        # it would affect all other instances, since this is typically called
        # on __init__
        processed_names = set()
        for d in defaults:
            name, default = d[0], copy.copy(d[1])
            processed_names.add(name)
            self._variable_defaults[name] = default
            # Set the attribute directly using the resolved value
            # (user config > global defaults > variable defaults)
            if name in self._user_config:
                value = self._user_config[name]
            elif name in self.global_defaults:
                value = self.global_defaults[name]
            else:
                # Don't overwrite methods/properties defined on the class
                # when using the default value
                class_attr = getattr(type(self), name, None)
                if class_attr is not None and (
                    callable(class_attr) or isinstance(class_attr, property)
                ):
                    continue
                value = default
            setattr(self, name, value)

        # Also set any global_defaults that weren't in the defaults list
        for name, value in self.global_defaults.items():
            if name not in processed_names and not hasattr(self, name):
                setattr(self, name, value)

    def _apply_global_defaults(self):
        """Apply global_defaults for attributes that have their default value.

        This should be called after global_defaults might have been set,
        e.g. in _configure methods.
        """
        # First, apply any new global_defaults
        for name, global_value in self.global_defaults.items():
            if name in self._user_config:
                continue  # User config takes precedence
            if name in self._variable_defaults:
                # If current value equals the variable default, use global default
                current = getattr(self, name, None)
                if current == self._variable_defaults[name]:
                    setattr(self, name, global_value)
            elif not hasattr(self, name):
                # Not in defaults list, just set it
                setattr(self, name, global_value)

        # Second, reset any values that are no longer in global_defaults
        # back to their variable defaults (if not in user_config)
        for name, var_default in self._variable_defaults.items():
            if name in self._user_config:
                continue  # User config takes precedence
            if name in self.global_defaults:
                continue  # Still in global_defaults
            # Not in user_config or global_defaults, reset to variable default
            setattr(self, name, var_default)

    def _find_default(self, name):
        """Returns a tuple (found, value)"""
        defaults = self._variable_defaults.copy()
        defaults.update(self.global_defaults)
        defaults.update(self._user_config)
        if name in defaults:
            return (True, defaults[name])
        else:
            return (False, None)


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
