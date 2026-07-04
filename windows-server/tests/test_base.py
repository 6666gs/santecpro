"""Tests for santecpro.instruments.base."""

import logging

import pytest
from unittest.mock import MagicMock, patch, call
from santecpro.instruments.base import BaseInstrument
from santecpro.exceptions import InstrumentConnectionError


class TestBaseInstrument:
    def test_connect_opens_resource(self, mock_resource_manager):
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        mock_resource_manager.open_resource.assert_called_once_with("GPIB0::10::INSTR")

    def test_connect_sets_terminator(self, mock_resource_manager, mock_resource):
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        assert mock_resource.write_termination == "\r"
        assert mock_resource.read_termination == "\r"

    def test_connect_sets_separate_read_terminator(self, mock_resource_manager, mock_resource):
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR", terminator="\r", read_terminator="\n")
        assert mock_resource.write_termination == "\r"
        assert mock_resource.read_termination == "\n"

    def test_connect_already_connected_raises(self, mock_resource_manager):
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        with pytest.raises(InstrumentConnectionError, match="(?i)already connected"):
            inst.connect("GPIB0::10::INSTR")

    def test_disconnect_closes_resource(self, mock_resource_manager, mock_resource):
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        inst.disconnect()
        mock_resource.close.assert_called_once()
        assert inst._resource is None

    def test_query_sends_command_and_returns_response(self, mock_resource_manager, mock_resource):
        mock_resource.query.return_value = "5.000\r\n"
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        result = inst.query("POW:LEV?")
        mock_resource.query.assert_called_once_with("POW:LEV?")
        assert result == "5.000"

    def test_write_sends_command(self, mock_resource_manager, mock_resource):
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        inst.write("POW:LEV 5")
        mock_resource.write.assert_called_with("POW:LEV 5")

    def test_read_returns_response(self, mock_resource_manager, mock_resource):
        mock_resource.read.return_value = "OK"
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        result = inst.read()
        assert result == "OK"

    def test_idn_returns_identity(self, mock_resource_manager, mock_resource):
        mock_resource.query.return_value = "SANTEC,TSL-550,12345,1.00"
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        assert inst.idn == "SANTEC,TSL-550,12345,1.00"
        mock_resource.query.assert_called_with("*IDN?")

    def test_timeout_property(self, mock_resource_manager, mock_resource):
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        assert inst.timeout == 5000
        inst.timeout = 10000
        assert mock_resource.timeout == 10000

    def test_query_when_not_connected_raises(self, mock_resource_manager):
        inst = BaseInstrument(mock_resource_manager)
        with pytest.raises(InstrumentConnectionError, match="(?i)not connected"):
            inst.query("*IDN?")

    def test_write_when_not_connected_raises(self, mock_resource_manager):
        inst = BaseInstrument(mock_resource_manager)
        with pytest.raises(InstrumentConnectionError, match="(?i)not connected"):
            inst.write("POW:LEV 5")


class TestScpiTrace:
    def test_trace_logs_queries(self, mock_resource_manager, mock_resource, caplog):
        mock_resource.query.return_value = "5.000"
        inst = BaseInstrument(mock_resource_manager, trace=True)
        inst.connect("GPIB0::10::INSTR")
        with caplog.at_level(logging.DEBUG, logger="santecpro.trace"):
            inst.query("POW:LEV?")
        assert "POW:LEV?" in caplog.text
        assert "5.000" in caplog.text

    def test_trace_logs_writes(self, mock_resource_manager, mock_resource, caplog):
        inst = BaseInstrument(mock_resource_manager, trace=True)
        inst.connect("GPIB0::10::INSTR")
        with caplog.at_level(logging.DEBUG, logger="santecpro.trace"):
            inst.write("POW:LEV 5")
        assert "POW:LEV 5" in caplog.text

    def test_trace_disabled_by_default(self, mock_resource_manager, mock_resource, caplog):
        mock_resource.query.return_value = "5.000"
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        with caplog.at_level(logging.DEBUG, logger="santecpro.trace"):
            inst.query("POW:LEV?")
        assert "POW:LEV?" not in caplog.text
