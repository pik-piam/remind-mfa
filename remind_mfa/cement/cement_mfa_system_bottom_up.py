import flodym as fd

from remind_mfa.cement.cement_mfa_system_future import StockDrivenCementMFASystem
from remind_mfa.common.trade import TradeSet
from remind_mfa.common.data_blending import CriticallyDampedBlender

REDUCED_STOCK_TYPE = fd.Dimension(name="Reduced Stock Type", letter="u", items=["Res", "Com"])


class StockDrivenBottomUpCementMFASystem(StockDrivenCementMFASystem):

    def compute(self, td_in_use: fd.Stock, historic_trade: TradeSet):
        """
        Perform all computations for the MFA system.
        The building split and MI parameters for the bottom-up MFA should ultimately set the inflow,
        but the data only describes the splits/mi of the current stock of the bottom-up MFA.
        Here, we assume a constant split/MI in the historical period, which will rebuild
        the recently observed stock. Thereafter (in future), scenario-adjusted split/MI
        are applied to the inflow, and the stock is computed from there.
        Implementation approach:
        1. Compute the floorspace inflow (both historical and future) from the floorspace stock.
        2. Apply the split/MI to the floorspace inflow.
        3. Calculate the inflow-driven DSM to get the bottom-up concrete inflow.
        4. Apply the MI weighted split and MI to the td inflow (from `td_in_use` stock).
        5. Calculate the inflow-driven DSM to get the top-down concrete inflow (including splits).
        6. Blend td into bu stock where bu is available, use td everywhere else.
        7. Compute the complete MFA with the blended stock and historic trade.
        """

        self.compute_floorspace_stock()
        self.compute_bottom_up_stock()
        self.compute_top_down_stock(td_in_use)
        combined_stock = self.blend_stocks()
        super().compute(combined_stock, historic_trade, stock_is_cement=False)

    def compute_floorspace_stock(self):
        """Calculate the floorspace inflow from stock change + lifetime (stock-driven)."""
        prm = self.parameters
        stk = self.stocks

        stock = prm["floorspace"]  # TODO remove once mrmfa is fixed
        stock[{"t": [y for y in stock.dims["t"].items if y < 2000]}] = (
            0  # TODO remove once mrmfa is fixed
        )
        stk["floorspace"].stock = stock
        self._set_lifetime("floorspace")
        stk["floorspace"].compute()

    def compute_bottom_up_stock(self):
        """Add bu dimensions to the floorspace inflow and calculate the bu concrete stock
        (inflow-driven), assuming a constant split/MI over time.
        """
        stk = self.stocks

        stk["bu_in_use"].inflow[...] = self.concrete_from_floorspace(
            stk["floorspace"].inflow, self.parameters
        )
        self._set_lifetime("bu_in_use")
        stk["bu_in_use"].compute()

    def compute_top_down_stock(self, td_in_use: fd.Stock):
        """Resolve the top-down in-use stock into building dimensions (f, b):
        Add bu dimensions to the td inflow and recalculate the td stock (inflow-driven).
        Equivalent to floorspace approach. Necessary to translate inflow splits into stock splits.
        Building splits are only applied to concrete, mortar gets N/A label.
        """
        prm = self.parameters
        stk = self.stocks

        # BU shares are given with respect to floorspace
        # => needs to be weighted by MI for use in mass stock
        mi_weighted_split = (
            prm["function_buildings_split"]
            * prm["structure_buildings_split"]
            * prm["concrete_building_mi"]
        ).get_shares_over(("f", "b"))

        td_inflow = td_in_use.inflow.sum_over("k")
        stk["td_in_use"].inflow[{"m": "concrete"}] = (
            td_inflow[{"m": "concrete"}] * mi_weighted_split
        )
        stk["td_in_use"].inflow[{"m": "mortar", "f": "nan", "b": "nan"}] = td_inflow[
            {"m": "mortar"}
        ]
        self._set_lifetime("td_in_use")
        stk["td_in_use"].compute()

    def blend_stocks(self) -> fd.FlodymArray:
        """Combine the bu and td stocks into one:
        Blend smoothly between historic td and future bu stock where bu is available;
        the rest remains td stock.
        """
        stk = self.stocks
        td_stock_expanded = stk["td_in_use"].stock

        # Preparation: remove (parts of the) dimensions that are not present in bu
        reduced_bu_stock = stk["bu_in_use"].stock[self.reduced_dim_mask]
        reduced_td_stock = td_stock_expanded[
            {
                **self.reduced_dim_mask,
                "m": "concrete",
                "t": self.dims["h"],
            }
        ]

        # Lifetime independent blend
        blender = CriticallyDampedBlender(
            time=self.dims["t"].items,
            historical=reduced_td_stock.values,
            prediction=reduced_bu_stock.values,
        )
        blended_stock = fd.FlodymArray.full_like(
            other=reduced_bu_stock,
            fill_value=blender.blend(),
        )

        combined_stock = td_stock_expanded.copy()
        combined_stock[{**self.reduced_dim_mask, "m": "concrete"}] = blended_stock
        return combined_stock

    def _set_lifetime(self, stock_name: str):
        self.stocks[stock_name].lifetime_model.set_prms(
            mean=self.parameters["lifetime_mean"],
            std=self.parameters["lifetime_std"],
        )

    @staticmethod
    def concrete_from_floorspace(
        floorspace: fd.FlodymArray, prm: dict[str, fd.FlodymArray]
    ) -> fd.FlodymArray:
        """Concrete quantity (stock or inflow) from a floorspace quantity, resolved by
        building function (f) and structure (b).
        The splits always sum to 1; `get_shares_over` re-asserts this to signal to the
        reconciliation optimizer that changing the sum has no effect.
        """
        function_split = prm["function_buildings_split"].get_shares_over(("f",))
        structure_split = prm["structure_buildings_split"].get_shares_over(("b",))
        concrete = floorspace * function_split * structure_split * prm["concrete_building_mi"]
        # scale up building stock to account for hibernating (unused) stock
        total_concrete = concrete / (1.0 - prm["hibernating_stock_share"])
        return total_concrete

    @property
    def reduced_dim_mask(self):
        return {
            "s": REDUCED_STOCK_TYPE,
        }
