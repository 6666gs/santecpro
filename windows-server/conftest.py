"""Pytest bootstrap for the Windows server package.

Ensures this folder is importable (so ``import santecpro``, ``import server``,
``import stsprocess_api`` and ``import santec_dll_backend`` resolve) and provides
shared mock-instrument fixtures.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_resource():
    """A mock pyvisa.Resource that records queries and writes."""
    resource = MagicMock()
    resource.query.return_value = ""
    resource.read.return_value = ""
    resource.write.return_value = None
    resource.timeout = 5000
    resource.query_delay = 0.0
    resource.write_termination = "\r"
    resource.read_termination = "\r"
    return resource


@pytest.fixture
def mock_resource_manager(mock_resource):
    """A mock pyvisa.ResourceManager that returns mock_resource."""
    rm = MagicMock()
    rm.open_resource.return_value = mock_resource
    return rm
