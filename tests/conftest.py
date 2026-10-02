"""CI cannot hide missing integration dependencies behind skipped tests."""

import os

import pytest


def pytest_sessionfinish(session, exitstatus):
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if os.environ.get("FAIL_ON_SKIP") == "1" and reporter and reporter.stats.get("skipped"):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
