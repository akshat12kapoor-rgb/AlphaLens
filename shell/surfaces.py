"""
Run a surface's unmodified app.py inside the combined AlphaLens app.

stock_simulator/ and stock-valuation-dashboard/ both ship a top-level package
named `modules`, so they cannot share one interpreter's `sys.modules`. Swapping
`sys.modules` per page is not an option either: Streamlit runs every browser
session on its own thread, so two tabs on different surfaces would race.

Instead each surface's package is loaded once under a private name
(`_alphalens_simulator_modules`, ...), and its app.py is executed with a
per-namespace `__import__` that rewrites `modules` to that name. The rewrite
lives in the script's own `__builtins__`, so it also covers functions the script
defines and Streamlit calls later - notably the simulator's replay fragment.

This relies on the surface packages never importing each other as
`modules.<x>`; they currently only import third-party libraries.
"""
from __future__ import annotations

import builtins
import importlib
import importlib.util
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from types import CodeType, ModuleType

from streamlit.runtime.scriptrunner import magic

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Surface:
    key: str
    directory: Path

    @property
    def alias(self) -> str:
        return f"_alphalens_{self.key}_modules"

    @property
    def script(self) -> Path:
        return self.directory / "app.py"


SIMULATOR = Surface("simulator", ROOT / "stock_simulator")
VALUATION = Surface("valuation", ROOT / "stock-valuation-dashboard")
SENTIMENT_DIR = ROOT / "SentimentFinance"
BACKTESTER_DIR = ROOT / "AlgoBacktester"

_lock = threading.Lock()
_compiled: dict[str, tuple[int, CodeType]] = {}


def package(surface: Surface) -> ModuleType:
    """The surface's `modules` package, loaded once under its private alias."""
    with _lock:
        pkg = sys.modules.get(surface.alias)
        if pkg is None:
            init = surface.directory / "modules" / "__init__.py"
            spec = importlib.util.spec_from_file_location(
                surface.alias, init, submodule_search_locations=[str(init.parent)])
            pkg = importlib.util.module_from_spec(spec)
            sys.modules[surface.alias] = pkg
            spec.loader.exec_module(pkg)
        return pkg


def module(surface: Surface, name: str) -> ModuleType:
    """A submodule of a surface's package, e.g. module(SIMULATOR, "data_fetcher")."""
    package(surface)
    return importlib.import_module(f"{surface.alias}.{name}")


def _importer(surface: Surface):
    real_import = builtins.__import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and (name == "modules" or name.startswith("modules.")):
            package(surface)
            name = surface.alias + name[len("modules"):]
        return real_import(name, globals, locals, fromlist, level)

    return _import


def _code(surface: Surface) -> CodeType:
    """Compiled app.py, recompiled when the file changes so edits show up on the
    next rerun, as they would under `streamlit run`."""
    with _lock:
        mtime = surface.script.stat().st_mtime_ns
        cached = _compiled.get(surface.key)
        if cached is None or cached[0] != mtime:
            path = str(surface.script)
            # add_magic keeps `streamlit run` semantics (bare expressions render).
            tree = magic.add_magic(surface.script.read_text(), path)
            cached = _compiled[surface.key] = (mtime, compile(tree, path, "exec"))
        return cached[1]


def run(surface: Surface) -> None:
    """Execute the surface's app.py as the current page."""
    scoped_builtins = dict(vars(builtins), __import__=_importer(surface))
    namespace = {
        "__name__": "__main__",
        "__file__": str(surface.script),
        "__builtins__": scoped_builtins,
        # Surfaces check this to defer to the platform (shared ticker, no own
        # branding or page config). Absent when a surface runs standalone.
        "ALPHAOS_EMBEDDED": True,
    }
    exec(_code(surface), namespace)


def _add_path(directory: Path) -> None:
    path = str(directory)
    with _lock:
        if path not in sys.path:
            sys.path.insert(0, path)


def use_sentiment() -> None:
    """SentimentFinance is flat stdlib modules (feed, lexicon, sentiment) with no
    name clash, so it just goes on sys.path."""
    _add_path(SENTIMENT_DIR)


def use_backtester() -> None:
    """AlgoBacktester is stdlib modules (backtester, data_loader, strategies/)
    with no name clash either. Its `strategies` package is unrelated to the
    simulator's `modules.strategies`, which only ever loads under its alias."""
    _add_path(BACKTESTER_DIR)
