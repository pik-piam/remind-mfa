import flodym as fd
import numpy as np


class InflowDrivenHistoricCementMFASystem(fd.MFASystem):
    
    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.compute_flows()
        self.compute_in_use_stock()
        self.check_mass_balance()

    def compute_flows(self):
        prm = self.parameters
        flw = self.flows

        # flow from data
        flw["cement_grinding => concrete_production"][...] = prm["cement_production"]

        # calculate value chain forwards
        flw["concrete_production => use"][...] = flw["cement_grinding => concrete_production"] / prm["cement_ratio"]  * prm["use_split"]

        # calculate value chain backwards
        flw["clinker_production => cement_grinding"][...] = flw["cement_grinding => concrete_production"] * prm["clinker_ratio"]
        flw["raw_meal_preparation => clinker_production"][...] = flw["clinker_production => cement_grinding"]
        flw["sysenv => raw_meal_preparation"][...] = flw["raw_meal_preparation => clinker_production"]

        # sysenv flows for mass balance: they represent net inflow of other material use minus waste
        flw["sysenv => cement_grinding"][...] = flw["cement_grinding => concrete_production"][...] * (1 - prm["clinker_ratio"])
        flw["sysenv => concrete_production"][...] = flw["concrete_production => use"][...] - flw["cement_grinding => concrete_production"][...]

        # TODO: find out waste rates
        flw["sysenv => clinker_production"][...] = fd.FlodymArray(dims=self.dims["h", "r",])


    def compute_in_use_stock(self):
        prm = self.parameters
        flw = self.flows
        stk = self.stocks

        # in use
        stk["historic_in_use"].inflow[...] = flw["concrete_production => use"]
        stk["historic_in_use"].lifetime_model.set_prms(
            mean=prm["use_lifetime_mean"],
            std=prm["use_lifetime_std"],
        )
        stk["historic_in_use"].compute()

        # end of life
        flw["use => eol"][...] = stk["historic_in_use"].outflow
        stk["historic_eol"].inflow[...] = flw["use => eol"]
        stk["historic_eol"].outflow[...] = fd.FlodymArray(dims=self.dims["h", "r", "s"])
        stk["historic_eol"].compute()
        flw["eol => sysenv"][...] = stk["historic_eol"].outflow




