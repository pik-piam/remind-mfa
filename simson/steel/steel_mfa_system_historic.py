import flodym as fd

from simson.common.trade import TradeSet
from simson.common.data_blending import blend


class InflowDrivenHistoricSteelMFASystem(fd.MFASystem):
    trade_set: TradeSet

    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.compute_trade()
        self.calc_sector_split()
        self.compute_flows()
        self.compute_in_use_stock()
        self.check_mass_balance()

    def compute_trade(self):
        """
        Create a trade module that stores and calculates the trade flows between regions and sectors.
        """
        for name, trade in self.trade_set.markets.items():
            trade.imports[...] = self.parameters[f"{name}_imports"]
            trade.exports[...] = self.parameters[f"{name}_exports"]
        self.trade_set.balance(to="maximum")

    def compute_flows(self):
        prm = self.parameters
        flw = self.flows
        trd = self.trade_set

        aux = {
            "net_intermediate_trade": self.get_new_array(dim_letters=("h", "r", "i")),
            "fabrication_inflow_by_sector": self.get_new_array(dim_letters=("h", "r", "g")),
            "fabrication_loss": self.get_new_array(dim_letters=("h", "r", "g")),
            "fabrication_error": self.get_new_array(dim_letters=("h", "r")),
        }

        # fmt: off
        flw["sysenv => forming"][...] = prm["production_by_intermediate"]
        flw["forming => ip_market"][...] = prm["production_by_intermediate"] * prm["forming_yield"]
        flw["forming => sysenv"][...] = flw["sysenv => forming"] - flw["forming => ip_market"]

        flw["ip_market => sysenv"][...] = trd["intermediate"].exports
        flw["sysenv => ip_market"][...] = trd["intermediate"].imports

        aux["net_intermediate_trade"][...] = flw["sysenv => ip_market"] - flw["ip_market => sysenv"]
        flw["ip_market => fabrication"][...] = flw["forming => ip_market"] + aux["net_intermediate_trade"]

        aux["fabrication_inflow_by_sector"][...] = flw["ip_market => fabrication"] * prm["sector_split"]

        aux["fabrication_error"] = flw["ip_market => fabrication"] - aux["fabrication_inflow_by_sector"]

        flw["fabrication => use"][...] = aux["fabrication_inflow_by_sector"] * prm["fabrication_yield"]
        aux["fabrication_loss"][...] = aux["fabrication_inflow_by_sector"] - flw["fabrication => use"]
        flw["fabrication => sysenv"][...] = aux["fabrication_error"] + aux["fabrication_loss"]

        # Recalculate indirect trade according to available inflow from fabrication
        trd["indirect"].exports[...] = trd["indirect"].exports.minimum(flw["fabrication => use"])
        trd["indirect"].balance(to="minimum")

        flw["sysenv => use"][...] = trd["indirect"].imports
        flw["use => sysenv"][...] = trd["indirect"].exports
        # fmt: on

    def calc_sector_split(self) -> fd.FlodymArray:
        """Blend over GDP per capita between typical sector splits for low and high GDP per capita regions."""
        self.parameters["sector_split"] = fd.Parameter(
            dims=self.dims["h", "r", "g"], name="sector_split"
        )
        self.parameters["sector_split"][...] = blend(
            target_dims=self.dims["h", "r", "g"],
            y_lower=self.parameters["sector_split_low"],
            y_upper=self.parameters["sector_split_high"],
            x=self.parameters["gdppc"][{"t": self.dims["h"]}],
            x_lower=self.parameters["secsplit_gdppc_low"],
            x_upper=self.parameters["secsplit_gdppc_high"],
            type="poly_mix",
        )

    def compute_in_use_stock(self):
        flw = self.flows
        stk = self.stocks
        prm = self.parameters
        flw = self.flows

        stk["historic_in_use"].inflow[...] = (
            flw["fabrication => use"] + flw["sysenv => use"] - flw["use => sysenv"]
        )

        stk["historic_in_use"].lifetime_model.set_prms(
            mean=prm["lifetime_mean"], std=prm["lifetime_std"]
        )

        stk["historic_in_use"].compute()  # gives stocks and outflows corresponding to inflow

        flw["use => sysenv"][...] += stk["historic_in_use"].outflow
