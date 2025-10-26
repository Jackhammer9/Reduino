"""Shared pytest fixtures and helpers."""

import re
import textwrap

import pytest


def deindent(code: str) -> str:
    """Remove common indentation and leading/trailing blank lines."""

    return textwrap.dedent(code).strip("\n")


def normalize_ws(s: str) -> str:
    """Collapse excess whitespace for resilient textual comparisons."""

    lines = [re.sub(r"\s+", " ", ln).strip() for ln in s.strip().splitlines()]
    return "\n".join(ln for ln in lines if ln)


@pytest.fixture
def src():
    """Return a helper that normalises indentation in code snippets."""

    return deindent


@pytest.fixture
def norm():
    """Return a helper that normalises whitespace in generated code."""

    return normalize_ws
