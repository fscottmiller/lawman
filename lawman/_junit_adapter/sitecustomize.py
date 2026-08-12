"""Attach one JUnit writer to the otherwise exact ``python -m unittest`` run."""

from __future__ import annotations

import atexit
import importlib
import os
from typing import Any

xmlrunner = importlib.import_module("xmlrunner")
unittest_main = importlib.import_module("unittest.main")
report = open(os.environ["LAWMAN_JUNIT_REPORT"], "wb")
atexit.register(report.close)


def _initialize(self: Any, *args: Any, **kwargs: Any) -> None:
    """Build unittest's runner with one stream-backed JUnit document."""
    kwargs.pop("output", None)
    kwargs.pop("outsuffix", None)
    xmlrunner.XMLTestRunner.__init__(self, *args, output=report, outsuffix="", **kwargs)


JUnitRunner = type("JUnitRunner", (xmlrunner.XMLTestRunner,), {"__init__": _initialize})
setattr(unittest_main, "TextTestRunner", JUnitRunner)
if hasattr(unittest_main, "runner"):
    setattr(unittest_main.runner, "TextTestRunner", JUnitRunner)
