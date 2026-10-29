import flodym as fd

from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.common.trade import TradeSet
from remind_mfa.cement.cement_config import CementCfg


class InflowDrivenHistoricalCementMFASystem(CommonMFASystem):
    """Top-down historical cement MFA system, driven by inflows."""

    cfg: CementCfg

    def compute(self) -> None:
        """
        Perform all computations for the MFA system.
        """
        self.fill_trade()
        self.balance_trade()
        prm, trd, flw, stk = self.mfa_stats()
        self.cap_historical_net_exports_to_supply(trd["cement"], prm["cement_production"])
        self.compute_stock(prm, trd, flw, stk)
        self.compute_other_flows(prm, trd, flw, stk)
        self.check_mass_balance()
        self.check_flows()

    def balance_trade(self) -> None:
        """
        Balance trade data to global imports.
        This best reflects high historical US imports according to USGS DS140.
        Note that cap_historical_net_exports_to_supply re-balances to the minimum in the
        years where it has to cap net exports.
        """
        self.trade_set.balance(to="imports")

    def mfa_stats(
        self,
    ) -> tuple[
        dict[str, fd.Parameter], TradeSet, dict[str, fd.Flow], dict[str, fd.Stock]
    ]:
        prm = self.parameters
        trd = self.trade_set
        flw = self.flows
        stk = self.stocks
        return prm, trd, flw, stk

    @staticmethod
    def compute_stock(
        prm: dict[str, fd.Parameter],
        trd: TradeSet,
        flw: dict[str, fd.Flow],
        stk: dict[str, fd.Stock],
    ) -> fd.FlodymArray:
        """Compute relevant flows for stock build-up and compute the in-use stock.
        For reconciliation, returns in use stock."""

        # production
        flw["cement_production => cement_market"][...] = prm["cement_production"]

        # product production
        cement_use = (
            (flw["cement_production => cement_market"] + trd["cement"].net_imports)
            * (1 - prm["cement_losses"])
            * prm["end_use_split"].get_shares_over("u") # only required for reconcilation.
        )
        flw["cement_market => construction"][...] = cement_use * prm[
            "construction_material_split"
        ].get_shares_over("m") # only required for reconcilation, split naturally sums to 1 anyways.
        product_by_material = flw["cement_market => construction"] / prm["cement_ratio"]
        flw["sysenv => construction"][...] = (
            product_by_material - flw["cement_market => construction"]
        )
        flw["construction => use"][...] = product_by_material.sum_over("m")

        stk["use"].inflow[...] = flw["construction => use"]
        stk["use"].lifetime_model.set_prms(
            mean=prm["lifetime_mean"],
            std=prm["lifetime_std"],
        )
        stk["use"].compute()

        return stk["use"].stock

    @staticmethod
    def compute_other_flows(
        prm: dict[str, fd.Parameter],
        trd: TradeSet,
        flw: dict[str, fd.Flow],
        stk: dict[str, fd.Stock],
    ) -> None:
        """Compute other flows for sanity checks like mass balance or negative flows."""

        # production
        flw["sysenv => cement_production"][...] = flw["cement_production => cement_market"]

        # cement losses during construction
        flw["cement_market => sysenv"][...] = (
            flw["cement_market => construction"] * prm["cement_losses"] / (1 - prm["cement_losses"])
        )

        # trade
        flw["cement_market => exports"][...] = trd["cement"].exports
        flw["imports => cement_market"][...] = trd["cement"].imports
        flw["exports => sysenv"][...] = flw["cement_market => exports"]
        flw["sysenv => imports"][...] = flw["imports => cement_market"]

        flw["use => sysenv"][...] = stk["use"].outflow
