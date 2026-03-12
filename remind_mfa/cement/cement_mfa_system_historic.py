from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.cement.cement_config import CementCfg
import flodym as fd
import numpy as np


class InflowDrivenHistoricCementMFASystem(CommonMFASystem):

    cfg: CementCfg

    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.balance_trade()
        self.compute_flows()
        self.compute_in_use_stock()
        self.compute_other_flows()
        self.check_mass_balance()
        self.check_flows()

    def balance_trade(self):
        self.trade_set.balance()

    def compute_flows(self):
        prm = self.parameters
        flw = self.flows
        trd = self.trade_set

        # production
        flw["prod_cement => market_cement"][...] = prm["cement_production"] * (1 - prm["cement_losses"])
        flw["prod_cement => sysenv"][...] = prm["cement_production"] * prm["cement_losses"]
        flw["sysenv => prod_cement"][...] = flw["prod_cement => market_cement"] + flw["prod_cement => sysenv"]

        # trade
        flw["market_cement => exports"][...] = trd["cement"].exports
        flw["imports => market_cement"][...] = trd["cement"].imports
        flw["exports => sysenv"][...] = flw["market_cement => exports"]
        flw["sysenv => imports"][...] = flw["imports => market_cement"]

        # use
        flw["market_cement => use"][...] = (
            (flw["prod_cement => market_cement"] + trd["cement"].net_imports)
            * self.parameters["stock_type_split"]
        )
        
    def compute_in_use_stock(self):
        prm = self.parameters
        flw = self.flows
        stk = self.stocks
        
        stk["in_use"].inflow[...] = flw["market_cement => use"]
        stk["in_use"].lifetime_model.set_prms(
            mean=prm["lifetime_mean"],
            std=prm["lifetime_rel_std"] * prm["lifetime_mean"],
        )
        stk["in_use"].compute()

    def compute_other_flows(self):
        flw = self.flows
        stk = self.stocks

        flw["use => sysenv"][...] = stk["in_use"].outflow
