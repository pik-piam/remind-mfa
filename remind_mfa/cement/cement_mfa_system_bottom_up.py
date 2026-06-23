import flodym as fd

from remind_mfa.cement.cement_mfa_system_future import StockDrivenCementMFASystem
from remind_mfa.cement.cement_parameter_reconciliation import CementParameterReconciliation
from remind_mfa.common.trade import TradeSet
from remind_mfa.common.data_blending import CriticallyDampedBlender


class StockDrivenBottomUpCementMFASystem(StockDrivenCementMFASystem):

    def compute(self, td_in_use: fd.Stock, historic_trade: TradeSet,  scale: bool = False):
        """
        Perform all computations for the MFA system.
        The building split and MI parameters for the bottom-up MFA should ultimately set the inflow,
        but the data only describes the splits/mi of the current stock of the bottom-up MFA.
        Here, we assume a constant split/MI in the historical period, which will rebuild
        the recently observed stock. Thereafter (in future), scenario-adjusted split/MI 
        are applied to the inflow, and the stock is computed from there.
        Implementation idea:
        1. Compute the floorspace inflow (both historical and future) from the floorspace stock.
        2. Apply the split/MI to the floorspace inflow.
        3. Calculate the inflow-driven DSM to get the bottom-up concrete inflow.
        4. Apply the MI weighted split and MI to the td inflow.
        5. Calculate the inflow-driven DSM to get the top-down concrete inflow (including splits).
        6. Blend td into bu stock where bu is available, use td everywhere else.
        7. Compute the complete MFA with the blended stock and historic trade.
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

        # Add bu dimensions to the inflow + calculate bu stock (inflow-driven)
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

        # Resolve the top-down in-use stock into building dimensions (f, b).
        # Add bu dimensions to the td infwlow and recalculate the td stock (inflow-driven)
        # Equivalent to floorspace approach. Necessary to translate inflow splits into stock splits.
        stk["td_in_use"].inflow[...] = td_in_use.inflow.sum_over("k") * mi_weighted_split
        stk["td_in_use"].lifetime_model.set_prms(
            mean=prm["lifetime_mean"],
            std=prm["lifetime_std"],
        )
        stk["td_in_use"].compute()
        td_stock_expanded = stk["td_in_use"].stock

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