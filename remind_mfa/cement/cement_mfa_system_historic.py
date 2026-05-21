from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.cement.cement_config import CementCfg


class InflowDrivenHistoricCementMFASystem(CommonMFASystem):
    """Top-down historical cement MFA system, driven by inflows."""

    cfg: CementCfg

    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.fill_trade()
        self.balance_trade()
        prm, trd, flw, stk = self.mfa_stats()
        self.compute_cement_stock(prm, trd, flw, stk)
        self.compute_other_flows(prm, trd, flw, stk)
        self.check_mass_balance()
        self.check_flows()

    def balance_trade(self):
        """
        Balance trade data to global imports.
        This best reflects high historical US imports according to USGS DS140.
        """
        self.trade_set.balance(to="imports")

    def mfa_stats(self):
        prm = self.parameters
        trd = self.trade_set
        flw = self.flows
        stk = self.stocks
        return prm, trd, flw, stk

    @staticmethod
    def compute_cement_stock(prm, trd, flw, stk):
        """Compute relevant flows for stock build-up and compute the stock.
        For reconciliation, returns in use stock."""

        # production
        flw["prod_cement => market_cement"][...] = prm["cement_production"] * (
            1 - prm["cement_losses"]
        )

        # use
        flw["market_cement => use"][...] = (
            flw["prod_cement => market_cement"] + trd["cement"].net_imports
        ) * prm["stock_type_split"]

        stk["in_use"].inflow[...] = flw["market_cement => use"]
        stk["in_use"].lifetime_model.set_prms(
            mean=prm["lifetime_mean"],
            std=prm["lifetime_std"],
        )
        stk["in_use"].compute()

        return stk["in_use"].stock

    @staticmethod
    def compute_other_flows(prm, trd, flw, stk):
        """Compute other flows for sanity checks like mass balance or negative flows."""

        # production
        flw["prod_cement => sysenv"][...] = prm["cement_production"] * prm["cement_losses"]
        flw["sysenv => prod_cement"][...] = (
            flw["prod_cement => market_cement"] + flw["prod_cement => sysenv"]
        )

        # trade
        flw["market_cement => exports"][...] = trd["cement"].exports
        flw["imports => market_cement"][...] = trd["cement"].imports
        flw["exports => sysenv"][...] = flw["market_cement => exports"]
        flw["sysenv => imports"][...] = flw["imports => market_cement"]

        flw["use => sysenv"][...] = stk["in_use"].outflow
