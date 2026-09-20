"""RiskManager — the only place capital, lot size and money figures meet.

Rules enforced here (from the product spec):
  * Never fabricate a lot size. No capital and no manual lot => no money
    figures, only an explicit disclaimer.
  * A manual lot always allows profit/loss amounts to be computed, with or
    without capital; only the risk-percent-of-capital figure needs capital.
  * Auto lot always needs capital; without it, auto mode cannot size the
    trade at all.

NOTE: money conversion here assumes the account currency matches the
symbol's quote currency (distance * lot_size * contract_size). Full
cross-currency conversion is a future refinement, not needed for v1.
"""
from __future__ import annotations

from core.market_data.models import Symbol
from core.risk.trade_plan import CapitalSource, LotSource, TradePlan
from core.risk.user_capital import UserCapitalConfig
from core.signals.selected_setup import SelectedSetup

NO_CAPITAL_NO_LOT_DISCLAIMER = (
    "Expected profit/loss and risk amount cannot be calculated precisely without "
    "capital or a manual lot size."
)
NO_CAPITAL_WITH_MANUAL_LOT_DISCLAIMER = (
    "Risk percentage of capital cannot be calculated because capital was not entered."
)


class RiskManager:
    def build_trade_plan(
        self,
        setup: SelectedSetup,
        symbol: Symbol,
        lot_mode: LotSource,
        manual_lot: float | None = None,
        capital: UserCapitalConfig | None = None,
    ) -> TradePlan:
        sl_distance = abs(setup.entry - setup.stop_loss)
        tp1_distance = abs(setup.take_profit_1 - setup.entry)
        tp2_distance = abs(setup.take_profit_2 - setup.entry)

        if lot_mode == LotSource.AUTO:
            if capital is None:
                return TradePlan(
                    setup_ref=setup,
                    lot_size=None,
                    lot_source=LotSource.AUTO,
                    capital_basis=CapitalSource.NONE,
                    risk_amount=None,
                    expected_profit_tp1=None,
                    expected_profit_tp2=None,
                    expected_loss=None,
                    financial_values_available=False,
                    financial_disclaimer=NO_CAPITAL_NO_LOT_DISCLAIMER,
                )
            risk_amount = capital.capital_amount * (capital.risk_percent / 100)
            lot_size = self._lot_for_risk(risk_amount, sl_distance, symbol)
            return TradePlan(
                setup_ref=setup,
                lot_size=lot_size,
                lot_source=LotSource.AUTO,
                capital_basis=CapitalSource.MANUAL_CAPITAL,
                risk_amount=risk_amount,
                expected_profit_tp1=self._distance_to_money(tp1_distance, lot_size, symbol),
                expected_profit_tp2=self._distance_to_money(tp2_distance, lot_size, symbol),
                expected_loss=risk_amount,
                risk_percent_of_capital=capital.risk_percent,
                financial_values_available=True,
            )

        # MANUAL lot mode.
        assert manual_lot is not None, "manual_lot is required when lot_mode is MANUAL"
        risk_amount = self._distance_to_money(sl_distance, manual_lot, symbol)
        risk_percent_of_capital = (risk_amount / capital.capital_amount * 100) if capital else None
        return TradePlan(
            setup_ref=setup,
            lot_size=manual_lot,
            lot_source=LotSource.MANUAL,
            capital_basis=CapitalSource.MANUAL_CAPITAL if capital else CapitalSource.NONE,
            risk_amount=risk_amount,
            expected_profit_tp1=self._distance_to_money(tp1_distance, manual_lot, symbol),
            expected_profit_tp2=self._distance_to_money(tp2_distance, manual_lot, symbol),
            expected_loss=risk_amount,
            risk_percent_of_capital=risk_percent_of_capital,
            financial_values_available=True,
            financial_disclaimer=None if capital else NO_CAPITAL_WITH_MANUAL_LOT_DISCLAIMER,
        )

    @staticmethod
    def _distance_to_money(distance: float, lot_size: float, symbol: Symbol) -> float:
        return distance * lot_size * symbol.contract_size

    @staticmethod
    def _lot_for_risk(risk_amount: float, sl_distance: float, symbol: Symbol) -> float:
        if sl_distance <= 0:
            raise ValueError("stop-loss distance must be positive to size a trade")
        return risk_amount / (sl_distance * symbol.contract_size)
