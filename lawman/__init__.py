"""Lawman: decide whether an intent may transition, and say why."""

from .decision import Contract, Decision, Evidence, Intent, LawmanError, decide

__all__ = ["Contract", "Decision", "Evidence", "Intent", "LawmanError", "decide"]
