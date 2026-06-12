import flodym as fd

from remind_mfa.cement.cement_mfa_system_future import StockDrivenCementMFASystem
from remind_mfa.cement.cement_parameter_reconciliation import CementParameterReconciliation
from remind_mfa.common.trade import TradeSet
from remind_mfa.common.data_blending import CriticallyDampedBlender


class StockDrivenBottomUpCementMFASystem(StockDrivenCementMFASystem):

    def compute(self, td_stock: fd.FlodymArray, historic_trade: TradeSet,  scale: bool = False):
        """
        Perform all computations for the MFA system.
        """
        if scale:
            raise NotImplementedError("Scaling not implemented for bottom-up system.")

        prm = self.parameters
        stk = self.stocks

        flow_split = (
            prm["function_buildings_split"]
            * prm["structure_buildings_split"]
            * prm["concrete_building_mi"]
            ).get_shares_over(("f", "b"))

        # Resolve the top-down in-use stock into building dimensions (f, b) by applying the split.
        # No dynamic stock model is needed here: because lifetimes do not depend on f or b
        td_stock_expanded = (td_stock * flow_split).sum_over("k")

        # Calculate floorspace stock:
        stk["floorspace"].stock = prm["floorspace"]
        stk["floorspace"].lifetime_model.set_prms(
            mean=prm["lifetime_mean"],
            std=prm["lifetime_std"],
        )
        stk["floorspace"].compute()

        # Calculate bottom_up inflow
        stk["bu_in_use"].inflow[...] = stk["floorspace"].inflow * flow_split * prm["concrete_building_mi"]
        stk["bu_in_use"].lifetime_model.set_prms(
            mean=prm["lifetime_mean"],
            std=prm["lifetime_std"],
        )
        stk["bu_in_use"].compute()

        reduced_bu_stock = stk["bu_in_use"].stock[self.reduced_dim_mask]
        reduced_td_stock = td_stock_expanded[self.reduced_dim_mask][{"m": "concrete"}][{"t": self.dims["h"]}]

        # Combine MFAs
        # blend smoothly between historic td and future bu
        blender = CriticallyDampedBlender(
            time=self.dims["t"].items,
            historical=reduced_td_stock.values,
            prediction=reduced_bu_stock.values,
            # lifetime independent blend,
        )
        blended_stock = fd.FlodymArray.full_like(
            other=reduced_bu_stock,
            fill_value=blender.blend(),
        )

        # prepare combined stock: place bu blended stock anywhere available, the rest remains td stock
        combined_stock = td_stock_expanded.copy()
        combined_stock[{**self.reduced_dim_mask, "m": "concrete"}] = blended_stock

        # compute combined mfa
        super().compute(combined_stock, historic_trade, stock_is_cement=False)

    @property
    def reduced_dim_mask(self):
        return {"s": CementParameterReconciliation._reduced_stock_type,}