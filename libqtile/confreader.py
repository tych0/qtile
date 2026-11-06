from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
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


class _MigratedSourceLoader(importlib.abc.Loader):
    """Execute a module from an in-memory (migrated) source string."""

    def __init__(self, path: str, source: str) -> None:
        self.path = path
        self.source = source

    def create_module(self, spec):
        return None

    def exec_module(self, module) -> None:
        exec(compile(self.source, self.path, "exec"), module.__dict__)


class _MigratedSourceFinder(importlib.abc.MetaPathFinder):
    """
    Serve migrated source for config files without touching them on disk, so we
    can check that the migrated config actually loads before writing it back.
    """

    def __init__(self, sources: dict[Path, str]) -> None:
        self.sources = sources

    def find_spec(self, fullname, path, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.origin is None:
            return None
        source = self.sources.get(Path(spec.origin).resolve())
        if source is None:
            return None
        return importlib.util.spec_from_file_location(
            fullname, spec.origin, loader=_MigratedSourceLoader(spec.origin, source)
        )


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

        If loading fails and ``auto_migrate`` is set, every available migration
        is applied (in memory) to the python files in the config's directory and
        the load is retried. The migrated files are only written back to disk
        (with backups of the originals) if the migrated config loads
        successfully; otherwise the original error is raised.
        """
        if not self.file_path:
            return

        path = Path(self.file_path)
        sys.path.insert(0, path.parent.as_posix())

        try:
            config = self._import_config(path)
        except Exception:
            if not auto_migrate:
                raise
            config = self._load_migrated(path)
            if config is None:
                raise

        self.update(**vars(config))

    def _import_config(self, path: Path, reload_submodules: bool = False):
        name = path.stem
        if name in sys.modules:
            self._reload_config_submodules(path)
            return importlib.reload(sys.modules[name])
        if reload_submodules:
            # A previous failed import may have left (unmigrated) submodules cached.
            self._reload_config_submodules(path)
        return importlib.import_module(name)

    def _load_migrated(self, path: Path):
        """
        Try to load the config with all migrations applied. Returns the loaded
        config module if successful (after writing the migrated sources back
        to disk), or None if migrations didn't help.
        """
        from libqtile.scripts.migrate import BACKUP_SUFFIX, file_and_backup, migrate_source

        migrated: dict[Path, tuple[str, str]] = {}
        for py, _ in file_and_backup(path.as_posix()):
            file = Path(py).resolve()
            try:
                original = file.read_text()
                updated = migrate_source(original)
            except ImportError:
                logger.info("libcst is not installed, not attempting config migration")
                return None
            except Exception:
                # e.g. a syntax error that libcst can't parse; nothing to migrate
                logger.debug("Failed to migrate %s", file, exc_info=True)
                continue
            if updated != original:
                migrated[file] = (original, updated)

        if not migrated:
            return None

        names = ", ".join(str(f) for f in migrated)
        logger.warning("Config failed to load, retrying with migrations applied to: %s", names)

        finder = _MigratedSourceFinder({f: updated for f, (_, updated) in migrated.items()})
        sys.meta_path.insert(0, finder)
        try:
            config = self._import_config(path, reload_submodules=True)
        except Exception:
            logger.exception("Config still fails to load after migration, not saving changes:")
            return None
        finally:
            sys.meta_path.remove(finder)

        for file, (original, updated) in migrated.items():
            backup = file.with_name(file.name + BACKUP_SUFFIX)
            try:
                backup.write_text(original)
                file.write_text(updated)
            except OSError:
                logger.exception("Failed to save migrated config to %s", file)
                continue
            logger.warning("Saved migrated config to %s (original backed up to %s)", file, backup)

        send_notification(
            "Configuration migrated",
            f"Your config was automatically migrated; backups saved with '{BACKUP_SUFFIX}' suffix.",
        )
        return config

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
