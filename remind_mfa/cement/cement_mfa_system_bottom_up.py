import flodym as fd

from remind_mfa.cement.cement_mfa_system_future import StockDrivenCementMFASystem
from remind_mfa.cement.cement_parameter_reconciliation import CementParameterReconciliation
from remind_mfa.common.trade import TradeSet
from remind_mfa.common.data_blending import CriticallyDampedBlender


class StockDrivenBottomUpCementMFASystem(StockDrivenCementMFASystem):

    def compute(self, td_stock: fd.FlodymArray, historic_trade: TradeSet,  scale: bool = False):
        """
        Perform all computations for the MFA system.
        The split and MI parameters for the bottom-up MFA should ultimately set the inflow,
        but currently set the stock of the bottom-up MFA.
        Here, we assume a constant split/MI in the historical period, which will rebuild
        the recently observed stock. Thereafter, the split/MI can be adjusted through scenarios.
        Implementation idea:
        1. Compute the floorspace inflow (both historical and future) from the floorspace stock.
        2. Apply the split/MI to the floorspace inflow to get the bottom-up concrete inflow.
        3. Take the bottom-up concrete stock and apply the MI weighted split to get bu dims.
        4. Blend td into bu stock where bu is available, use td everywhere else.
        5. Compute the complete MFA with the blended stock and historic trade.
        """
        if scale:
            raise NotImplementedError("Scaling not implemented for bottom-up system.")

        prm = self.parameters
        stk = self.stocks

        # ------------- Compute BU stock -------------
        # Calculate floorspace inflow from stock change + lifetime (stock-driven)
        stock = prm["floorspace"]
        stock[{'t': [y for y in stock.dims['t'].items if y < 2000]}] = 0
        stk["floorspace"].stock = stock
        stk["floorspace"].lifetime_model.set_prms(
            mean=prm["lifetime_mean"],
            std=prm["lifetime_std"],
        )
        stk["floorspace"].compute()

        # Add bu dimensions to the inflow + calculate bottom_up stock (inflow-driven)
        stk["bu_in_use"].inflow[...] = (
            stk["floorspace"].inflow
            * prm["function_buildings_split"]
            * prm["structure_buildings_split"]
            * prm["concrete_building_mi"]
        )
        stk["bu_in_use"].lifetime_model.set_prms(
            mean=prm["lifetime_mean"],
            std=prm["lifetime_std"],
        )
        stk["bu_in_use"].compute()

        # ------------- Compute TD stock -------------
        # BU shares are given with respect to floorspace 
        # => needs to be weighted by MI for use in mass stock
        mi_weighted_split = (
            prm["function_buildings_split"]
            * prm["structure_buildings_split"]
            * prm["concrete_building_mi"]
            ).get_shares_over(("f", "b"))

        # Resolve the top-down in-use stock into building dimensions (f, b) by applying the split.
        # No dynamic stock model is needed here: because lifetimes do not depend on f or b
        # Also, remove "k" dimension which is added again in super().compute()
        td_stock_expanded = (td_stock * mi_weighted_split).sum_over("k")

        # ------------- Blend BU and TD stocks -------------
        # Preparation: remove (parts of the) dimensions that are not present in bu
        reduced_bu_stock = stk["bu_in_use"].stock[self.reduced_dim_mask]
        #reduced_td_stock = td_stock_expanded[self.reduced_dim_mask][{"m": "concrete"}][{"t": self.dims["h"]}]
        reduced_td_stock = td_stock_expanded[{
            **self.reduced_dim_mask,
            "m": "concrete",
            "t": self.dims["h"],
        }]

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