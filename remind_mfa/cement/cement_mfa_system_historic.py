from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.cement.cement_config import CementCfg


class InflowDrivenHistoricCementMFASystem(CommonMFASystem):

    cfg: CementCfg

    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.compute_in_use_stock()
        self.compute_flows()
        self.check_mass_balance()
        self.check_flows()

    def compute_in_use_stock(self):
        prm = self.parameters
        stk = self.stocks
        cement_consumption = (1 - prm["cement_losses"]) * (
            prm["cement_production"] - prm["cement_trade"]
        )

        # in use
        stk["historic_cement_in_use"].inflow[...] = cement_consumption * prm["stock_type_split"]
        lifetime_rel_std = 0.4
        stk["historic_cement_in_use"].lifetime_model.set_prms(
            mean=prm["use_lifetime_mean"],
            std=lifetime_rel_std * prm["use_lifetime_mean"],
        )
        add_assumption_doc(
            type="expert guess",
            value=lifetime_rel_std,
            name="Standard deviation of historic use lifetime",
            description=f"The standard deviation of the historic use lifetime is set to {int(lifetime_rel_std * 100)} of the mean.",
        )
        stk["historic_cement_in_use"].compute()

    def compute_flows(self):
        flw = self.flows
        stk = self.stocks

        flw["sysenv => use"][...] = stk["historic_cement_in_use"].inflow
        flw["use => sysenv"][...] = stk["historic_cement_in_use"].outflow
