from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.cement.cement_config import CementCfg


class InflowDrivenHistoricalCementMFASystem(CommonMFASystem):
    """Top-down historical cement MFA system, driven by inflows."""

    cfg: CementCfg

    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.fill_trade()
        self.balance_trade()
        self.cap_historical_net_exports_to_supply(
            self.trade_set["cement"], self.parameters["cement_production"]
        )
        self.compute_flows_and_stock(self.parameters, self.trade_set, self.flows, self.stocks)
        self.check_mass_balance()
        self.check_flows()

    def balance_trade(self):
        """
        Balance trade data to global imports.
        This best reflects high historical US imports according to USGS DS140.
        Note that cap_historical_net_exports_to_supply re-balances to the minimum in the
        years where it has to cap net exports.
        """
        self.trade_set.balance(to="imports")

    @staticmethod
    def compute_flows_and_stock(prm, trd, flw, stk):
        """Compute all flows and the in-use stock. Static, as it is also used in the
        parameter reconciliation, which needs the in-use stock it returns."""

        # production
        flw["sysenv => cement_production"][...] = prm["cement_production"]
        flw["cement_production => cement_market"][...] = prm["cement_production"]

        # trade
        flw["imports => cement_market"][...] = trd["cement"].imports
        flw["cement_market => exports"][...] = trd["cement"].exports
        flw["sysenv => imports"][...] = trd["cement"].imports
        flw["exports => sysenv"][...] = trd["cement"].exports

        # construction
        cement_use = (
            (flw["cement_production => cement_market"] + trd["cement"].net_imports)
            * (1 - prm["cement_losses"])
            * prm["end_use_split"]
            * prm["construction_material_split"]
        )
        product_by_material = cement_use / prm["cement_ratio"]
        flw["sysenv => construction"][...] = product_by_material - cement_use
        flw["construction => use"][...] = product_by_material.sum_over("m")
        # construction losses are relative to total cement use
        flw["cement_market => construction"][...] = cement_use / (1 - prm["cement_losses"])
        flw["construction => sysenv"][...] = (
            flw["cement_market => construction"] * prm["cement_losses"]
        )

        # in-use stock
        stk["use"].inflow[...] = flw["construction => use"]
        stk["use"].lifetime_model.set_prms(
            mean=prm["lifetime_mean"],
            std=prm["lifetime_std"],
        )
        stk["use"].compute()
        flw["use => sysenv"][...] = stk["use"].outflow

        return stk["use"].stock
