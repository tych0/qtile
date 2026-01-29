import copy


class Configurable:
    global_defaults = {}  # type: dict

    def __init__(self, **config):
        self._variable_defaults = {}
        self._user_config = config
        # Set all user config values as instance attributes
        for name, value in config.items():
            setattr(self, name, value)

    def add_defaults(self, defaults):
        """Add defaults to this object, overwriting any which already exist"""
        # Since we can't check for immutability reliably, shallow copy the
        # value. If a mutable value were set and it were changed in one place
        # it would affect all other instances, since this is typically called
        # on __init__
        for d in defaults:
            name, default = d[0], copy.copy(d[1])
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
