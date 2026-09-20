import types

import pytest
from fastapi import HTTPException

from backend.routers.signals import AnalyzeRequest, _validate_risk_and_lot


def _settings(*, allow_custom_risk=False, allow_custom_lot=False):
    return types.SimpleNamespace(
        risk={"presets_percent": [0.25, 0.5, 1.0, 1.5, 2.0], "allow_custom_risk_percent": allow_custom_risk},
        lots={"presets": [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0], "allow_custom_lot": allow_custom_lot},
    )


def test_preset_risk_percent_and_auto_lot_is_valid():
    req = AnalyzeRequest(symbol="EURUSD", risk_percent=1.0, lot_mode="AUTO")
    _validate_risk_and_lot(req, _settings())  # should not raise


def test_custom_risk_percent_rejected_when_not_allowed():
    req = AnalyzeRequest(symbol="EURUSD", risk_percent=0.77, lot_mode="AUTO")
    with pytest.raises(HTTPException) as exc:
        _validate_risk_and_lot(req, _settings(allow_custom_risk=False))
    assert exc.value.status_code == 422


def test_custom_risk_percent_allowed_when_enabled():
    req = AnalyzeRequest(symbol="EURUSD", risk_percent=0.77, lot_mode="AUTO")
    _validate_risk_and_lot(req, _settings(allow_custom_risk=True))  # should not raise


def test_manual_lot_requires_lot_size():
    req = AnalyzeRequest(symbol="EURUSD", risk_percent=1.0, lot_mode="MANUAL")
    with pytest.raises(HTTPException) as exc:
        _validate_risk_and_lot(req, _settings())
    assert exc.value.status_code == 422


def test_custom_lot_rejected_when_not_allowed():
    req = AnalyzeRequest(symbol="EURUSD", risk_percent=1.0, lot_mode="MANUAL", lot_size=0.03)
    with pytest.raises(HTTPException):
        _validate_risk_and_lot(req, _settings(allow_custom_lot=False))


def test_preset_lot_is_valid():
    req = AnalyzeRequest(symbol="EURUSD", risk_percent=1.0, lot_mode="MANUAL", lot_size=0.05)
    _validate_risk_and_lot(req, _settings())  # should not raise


def test_negative_risk_percent_rejected():
    req = AnalyzeRequest(symbol="EURUSD", risk_percent=-1.0, lot_mode="AUTO")
    with pytest.raises(HTTPException):
        _validate_risk_and_lot(req, _settings(allow_custom_risk=True))


def test_negative_capital_rejected():
    req = AnalyzeRequest(symbol="EURUSD", risk_percent=1.0, lot_mode="AUTO", capital=-500)
    with pytest.raises(HTTPException):
        _validate_risk_and_lot(req, _settings())


def test_negative_lot_size_rejected():
    req = AnalyzeRequest(symbol="EURUSD", risk_percent=1.0, lot_mode="MANUAL", lot_size=-0.1)
    with pytest.raises(HTTPException):
        _validate_risk_and_lot(req, _settings(allow_custom_lot=True))
