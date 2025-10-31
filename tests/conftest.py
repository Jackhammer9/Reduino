"""Shared pytest fixtures and helpers."""

import re
import textwrap

import pytest


def deindent(code: str) -> str:
    """Remove common indentation and leading/trailing blank lines."""

    return textwrap.dedent(code).strip("\n")


def normalize_ws(text: str) -> str:
    """Collapse runs of whitespace for resilient textual comparisons."""

    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.strip().splitlines()]
    return "\n".join(line for line in lines if line)


@pytest.fixture
def src():
    """Return a helper that normalises indentation in code snippets."""

    return deindent


@pytest.fixture
def norm():
    """Return a helper that normalises whitespace in generated code."""

    return normalize_ws
