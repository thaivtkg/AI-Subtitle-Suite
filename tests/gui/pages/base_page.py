# -*- coding: utf-8 -*-
"""
Base Page Object for PySide6 Desktop GUI Automation.
Wraps the QtDriver and provides common page behaviors.
"""
from __future__ import annotations
from typing import Optional, Any
from PySide6.QtWidgets import QWidget
from tests.gui.drivers.qt_driver import QtDriver


class BasePage:
    """Base class for all Page Objects in the AI Subtitle Suite GUI test suite."""

    def __init__(self, driver: QtDriver):
        self.driver = driver
        self.window = driver.root_window

    def wait_ms(self, ms: int) -> None:
        self.driver.wait_ms(ms)

    def wait_until(self, condition_fn, timeout_ms: int = 5000, message: str = "") -> None:
        self.driver.wait_until(condition_fn, timeout_ms=timeout_ms, message=message)
