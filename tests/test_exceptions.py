"""Tests for santecpro.exceptions."""

import pytest
from santecpro.exceptions import (
    SantecError,
    InstrumentConnectionError,
    InstrumentOperationError,
)


def test_santec_error_has_message():
    err = SantecError("something broke")
    assert str(err) == "something broke"


def test_santec_error_has_error_code():
    err = SantecError("fail", error_code=-1)
    assert err.error_code == -1
    assert "fail" in str(err)


def test_santec_error_default_code():
    err = SantecError("fail")
    assert err.error_code is None


def test_connection_error_is_santec_error():
    err = InstrumentConnectionError("cannot connect")
    assert isinstance(err, SantecError)
    assert str(err) == "cannot connect"


def test_operation_error_is_santec_error():
    err = InstrumentOperationError("bad operation", error_code=-30)
    assert isinstance(err, SantecError)
    assert err.error_code == -30
