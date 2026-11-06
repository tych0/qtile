from __future__ import annotations

import importlib
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from types import FunctionType
from typing import Any, Literal

from libqtile.config import Group, IdleInhibitor, IdleTimer, Key, Mouse, Output, Rule, Screen
from libqtile.layout.base import Layout
from libqtile.log_utils import logger
from libqtile.utils import send_notification


class ConfigError(Exception):
    pass


class ConfigMigrated(Exception):
    """
    The config failed to load, but has been migrated on disk to a version that
    does. Qtile should re-exec itself to pick up the migrated config.
    """


# Scratch directory (inside the config directory) used to try out a migrated config.
MIGRATE_SUBDIR = ".qtile-migrate"


config_pyi_header = """
from collections.abc import Callable
from typing import Any
from typing import Literal
from types import FunctionType
from libqtile.config import Group, IdleInhibitor, IdleTimer, Key, Mouse, Output, Rule, Screen
from libqtile.layout.base import Layout

"""


class Config:
    # All configuration options
    keys: list[Key]
    mouse: list[Mouse]
    groups: list[Group]
    dgroups_key_binder: Any
    dgroups_app_rules: list[Rule]
    follow_mouse_focus: bool | Literal["click_or_drag_only"]
    focus_on_window_activation: Literal["focus", "smart", "urgent", "never"] | FunctionType
    focus_previous_on_window_remove: bool
    cursor_warp: bool
    layouts: list[Layout]
    floating_layout: Layout
    screens: list[Screen]
    auto_fullscreen: bool
    widget_defaults: dict[str, Any]
    extension_defaults: dict[str, Any]
    bring_front_click: bool | Literal["floating_only"]
    floats_kept_above: bool
    reconfigure_screens: bool
    screen_change_debounce_timeout: int | float
    wmname: str
    auto_minimize: bool
    # Really we'd want to check this Any is libqtile.backend.wayland.ImportConfig, but
    # doing so forces the import, creating a hard dependency for wlroots.
    wl_input_rules: dict[str, Any] | None
    wl_xcursor_theme: str | None
    wl_xcursor_size: int
    idle_timers: list[IdleTimer]
    idle_inhibitors: list[IdleInhibitor]
    fake_screens: list[Screen] | None
    generate_screens: Callable[[list[Output]], list[Screen]] | None

    def __init__(self, file_path=None, **settings):
        """Create a Config() object from settings

        Only attributes found in Config.__annotations__ will be added to object.
        config attribute precedence is 1.) **settings 2.) self 3.) default_config
        """
        self.file_path = file_path
        self.update(**settings)

    def update(self, **settings):
        from libqtile.resources import default_config

        default = vars(default_config)
        for key in Config.__annotations__.keys():
            try:
                value = settings[key]
            except KeyError:
                if key == "screens" and (
                    settings.get("generate_screens") is not None
                    or getattr(self, "generate_screens", None) is not None
                    or settings.get("fake_screens") is not None
                    or getattr(self, "fake_screens", None) is not None
                ):
                    value = []
                else:
                    value = getattr(self, key, default.get(key, None))
            setattr(self, key, value)

    def _reload_config_submodules(self, path: Path) -> None:
        """Reloads python files from same folder as config file."""
        folder = path.parent
        for module in sys.modules.copy().values():
            # Skip built-ins and anything with no filepath.
            if hasattr(module, "__file__") and module.__file__ is not None:
                subpath = Path(module.__file__)

                if subpath == path:
                    # do not reevaluate config itself here, we want only
                    # reload all submodules. Also we cant reevaluate config
                    # here, because it will cache all current modules before they
                    # are reloaded. Thus, config file should be reloaded after
                    # this routine.
                    continue

                # Check if the module is in the config folder or subfolder
                # and the file still exists.  If so, reload it
                if folder in subpath.parents and subpath.exists():
                    importlib.reload(module)

    def load(self, auto_migrate: bool = True) -> None:
        """
        Load the config file.

        If loading fails and ``auto_migrate`` is set, the config directory's
        python files are migrated into a scratch subdirectory and load tested
        from there. If that works, the migrated files are moved over the
        originals (which are kept as backups) and ConfigMigrated is raised, so
        the caller can re-exec qtile with the migrated config. Otherwise the
        original error is raised.
        """
        if not self.file_path:
            return

        path = Path(self.file_path)
        sys.path.insert(0, path.parent.as_posix())

        try:
            config = self._import_config(path)
        except Exception as error:
            if not auto_migrate or not self._migrate(path):
                raise
            raise ConfigMigrated(f"Config was migrated after failing to load: {error}") from error

        self.update(**vars(config))

    def _import_config(self, path: Path):
        name = path.stem
        if name in sys.modules:
            self._reload_config_submodules(path)
            return importlib.reload(sys.modules[name])
        return importlib.import_module(name)

    @staticmethod
    def _forget_config_modules(folder: Path) -> None:
        """Drop any modules loaded from the config folder (or below) from sys.modules."""
        for name, module in list(sys.modules.items()):
            file = getattr(module, "__file__", None)
            if file is not None and folder in Path(file).parents:
                del sys.modules[name]

    def _migrate(self, path: Path) -> bool:
        """
        Migrate the config into a subdirectory and load test it from there.
        If it loads, move the migrated files over the originals. Returns True
        if the config was migrated.
        """
        from libqtile.scripts.migrate import BACKUP_SUFFIX, migrate_source

        folder = path.parent.resolve()
        scratch = folder / MIGRATE_SUBDIR
        shutil.rmtree(scratch, ignore_errors=True)
        try:
            scratch.mkdir()
            changed = []
            for py in folder.glob("*.py"):
                original = py.read_text()
                try:
                    updated = migrate_source(original)
                except ImportError:
                    logger.info("libcst is not installed, not attempting config migration")
                    return False
                except Exception:
                    # e.g. a syntax error that libcst can't parse
                    logger.debug("Failed to migrate %s", py, exc_info=True)
                    updated = original
                (scratch / py.name).write_text(updated)
                if updated != original:
                    changed.append(py.name)

            if not changed:
                return False

            logger.warning("Config failed to load, trying migrated config in %s", scratch)
            self._forget_config_modules(folder)
            try:
                Config(scratch / path.name).load(auto_migrate=False)
            except Exception:
                logger.exception(
                    "Config still fails to load after migration, not saving changes:"
                )
                return False
            finally:
                self._forget_config_modules(folder)
                while scratch.as_posix() in sys.path:
                    sys.path.remove(scratch.as_posix())

            for name in changed:
                shutil.copyfile(folder / name, folder / (name + BACKUP_SUFFIX))
                os.replace(scratch / name, folder / name)
                logger.warning("Migrated %s (original backed up with %s)", name, BACKUP_SUFFIX)
        except OSError:
            logger.exception("Failed to migrate config:")
            return False
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

        send_notification(
            "Configuration migrated",
            f"Your config was automatically migrated; backups saved with '{BACKUP_SUFFIX}' suffix.",
        )
        return True

    def validate(self) -> None:
        """
        Validate the configuration against the X11 core, if it makes sense.
        """
        try:
            from libqtile.backend.x11 import core
        except ImportError:
            return

        valid_keys = core.get_keys()
        valid_mods = core.get_modifiers()
        # we explicitly do not want to set self.keys and self.mouse above,
        # because they are dynamically resolved from the default_config. so we
        # need to ignore the errors here about missing attributes.
        for k in self.keys:
            if isinstance(k.key, str) and k.key.lower() not in valid_keys:
                raise ConfigError(f"No such key: {k.key}")
            for m in k.modifiers:
                if m.lower() not in valid_mods:
                    raise ConfigError(f"No such modifier: {m}")
        for ms in self.mouse:
            for m in ms.modifiers:
                if m.lower() not in valid_mods:
                    raise ConfigError(f"No such modifier: {m}")
