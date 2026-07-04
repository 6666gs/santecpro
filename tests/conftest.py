"""Shared test fixtures for santecpro tests."""

import pytest
from unittest.mock import MagicMock, PropertyMock


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
