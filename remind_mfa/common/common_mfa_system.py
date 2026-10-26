import logging
import sys
import numpy as np
import flodym as fd
from typing import ClassVar, Literal, Optional

from remind_mfa.common.trade import TradeSet, Trade
from remind_mfa.common.common_config import CommonCfg
from remind_mfa.common.helpers import clip_negative_arr
from remind_mfa.common.data_blending import critically_damped_blend, FLOW_APPROACHING_TIME
from remind_mfa.common.assumptions_doc import add_assumption_doc


class CommonMFASystem(fd.MFASystem):

    cfg: CommonCfg
    trade_set: Optional[TradeSet] = None
    lifetime_n_pts_per_interval: ClassVar[int] = 1
    """Number of points per time interval of the in-use stock lifetime models."""

    def compute_use_stock(
        self,
        stock_projection: fd.FlodymArray,
        use_stock_name: str = "use",
    ):
        """Compute the in-use stock from the stock projection.

        First, a StockDrivenDSM computation on the dims of the stock projection yields the
        inflow, which is then adjusted (see ``adjust_inflow``). The in-use stock is recomputed as
        InflowDrivenDSM with the resulting inflow.

        Args:
            stock_projection (fd.FlodymArray): Projected in-use stock. May lack dims of the
                in-use stock, if ``adjust_inflow`` adds them.
            use_stock_name (str): Name of the in-use stock. Defaults to "use".
        """
        stock = fd.StockDrivenDSM(
            dims=stock_projection.dims,
            stock=stock_projection.to_class(fd.StockArray),
            lifetime_model=self.cfg.model_switches.lifetime_model,
        )
        self.set_prms_and_compute(stock)

        inflow = self.adjust_inflow(stock.inflow)
        self.stocks[use_stock_name].inflow[...] = inflow
        self.set_prms_and_compute(self.stocks[use_stock_name])

    def set_prms_and_compute(self, stock: fd.Stock):
        """Set the lifetime model parameters and compute the stock.

        Args:
            stock (fd.Stock): Stock to set parameters for and compute.
        """
        stock.lifetime_model.n_pts_per_interval = self.lifetime_n_pts_per_interval
        stock.lifetime_model.set_prms(
            mean=self.parameters["lifetime_mean"],
            std=self.parameters["lifetime_std"],
        )
        stock.compute()

    def adjust_inflow(self, inflow: fd.FlodymArray) -> fd.FlodymArray:
        """Smooth the transition of the in-use stock inflow from historical to future years
        with a critically damped blend, and correct any negative inflows to zero.

        Args:
            inflow (fd.FlodymArray): Inflow resulting from a StockDrivenDSM computation.

        Returns:
            fd.FlodymArray: Blended and non-negative inflow.
        """
        blended_inflow = critically_damped_blend(
            inflow,
            n_historical=self.dims["h"].len,
            n_trend_years=self.parameters["n_trend_years"],
            approaching_time=FLOW_APPROACHING_TIME,
        )
        blended_inflow.name = "In-use stock inflow"
        add_assumption_doc(
            type="model assumption",
            name="Critically damped blend of in-use stock inflow",
            value=FLOW_APPROACHING_TIME,
            description=(
                "The in-use stock inflow resulting from the stock-driven model is blended smoothly "
                "from historical trends to the future values with a critically damped blend. "
                "The in-use stock is then recomputed from the blended inflow. "
                "The value is the approaching time in years."
            ),
        )
        return clip_negative_arr(blended_inflow)

    def compute_hibernation(self, outflow: fd.FlodymArray) -> fd.FlodymArray:
        """Compute the hibernating share of the in-use outflow and the hibernating stock.

        Computes the stock ``hibernating``, which has no outflow, from the parameter
        ``hibernation_share``. The flow ``use => hibernating`` is left to the caller.

        Args:
            outflow (fd.FlodymArray): Outflow of the in-use stock.

        Returns:
            fd.FlodymArray: Part of the outflow that hibernates.
        """
        hibernation_inflow = outflow * self.parameters["hibernation_share"]
        self.stocks["hibernating"].inflow[
            ...
        ] = hibernation_inflow  # extra line in case of lower dimensionality of hibernation stock
        self.stocks["hibernating"].compute()
        return hibernation_inflow

    def fill_trade(self):
        """
        Fill trade from parameters named after the scheme [market_name]_imports and [market_name]_exports.
        """
        for name, trade in self.trade_set.markets.items():
            trade.imports[...] = self.parameters[f"{name}_imports"]
            trade.exports[...] = self.parameters[f"{name}_exports"]

    def cap_historical_net_exports_to_supply(self, trade: Trade, supply: fd.FlodymArray):
        """Cap a historical trade's *net* exports at the available domestic supply so downstream
        flows cannot go negative when historical net exports exceed domestic production, then
        re-balance globally. Gross exports may still exceed supply where they are covered by
        imports (stop-over / re-export trade), since manufacturing inflow = supply + imports -
        exports only requires exports - imports <= supply.
        Net exports are calculated per dimension (e.g. polymer type/polymer/end use) and then summed up,
        because positive net imports (imports > exports) of one good cannot be balanced by
        re-exporting a different good, so that net amount is not stop-over trade and must be consumed.

        ``balance`` re-inflates the opposite (import) side and thereby partially reintroduces
        the violation, so the cap and balance are iterated to convergence.
        Warns with the region/category coordinates where net exports had to be reduced.

        Only called by the historical MFA systems.
        """
        self._cap_net_trade(trade, limit=supply, direction="exports", warn=True)

    def cap_net_imports_to_capacity(self, trade: Trade, capacity: fd.FlodymArray):
        """Cap a trade's *net* imports at the domestic capacity to absorb them, then re-balance
        globally by reducing the exports of the other regions, which keep that material.

        Mirrors :meth:`cap_historical_net_exports_to_supply` with imports and exports swapped,
        but is meant for future trade, where the capping is a model mechanism and not a data
        correction, so it does not warn. Pass an infinite capacity for items that must not be
        capped, e.g. historical years.
        """
        self._cap_net_trade(trade, limit=capacity, direction="imports", warn=False)

    def _cap_net_trade(
        self,
        trade: Trade,
        limit: fd.FlodymArray,
        direction: Literal["imports", "exports"],
        warn: bool,
    ):
        """Cap a trade's positive net flow in ``direction`` at ``limit`` and re-balance globally
        (see :meth:`Trade.cap_net`). If ``warn`` is set, warns where the cap was binding.
        """
        tolerance = 10 * self._absolute_float_precision
        excess, net_flow_total = trade.cap_net(limit, direction=direction, tolerance=tolerance)
        if warn and (excess.values > tolerance).any():
            self._warn_historical_net_trade_cap(
                trade.name or "trade",
                excess,
                net_flow_total,
                tolerance,
                sys.float_info.epsilon,
                direction=direction,
            )

    def redistribute_surplus(self, trade: Trade, supply: fd.FlodymArray, demand: fd.FlodymArray):
        """Redistribute regional surplus between regions via an auxiliary trade.

        Where a region's ``supply`` exceeds the domestic ``demand`` it can feed, the surplus is
        exported; regions with headroom (``demand`` above their ``supply``) import it.
        Exports are seeded with the surplus and imports with the headroom, then both are balanced
        to the smaller global total (``to="minimum"``). Each region thus imports
        ``min(total surplus, total headroom) * headroom_share``, which never exceeds its headroom.
        If the total surplus exceeds the total headroom, the exporting regions keep the remainder.

        Overwrites the trade's imports and exports.
        """
        trade.exports[...] = (supply - demand).maximum(0)
        trade.imports[...] = (demand - supply).maximum(0)
        trade.balance(to="minimum")

    def cap_historical_net_imports_to_demand(
        self,
        trade: Trade,
        demand: fd.FlodymArray,
        category_dim: Optional[str] = None,
    ):
        """Cap a trade's net imports at domestic demand so downstream production / manufacturing
        flows cannot go negative.

        If ``category_dim`` is given (e.g. polymer 'p' for plastics primary trade), the excess of
        net imports over demand is first reassigned to the sibling categories (see
        :meth:`_reassign_net_imports_within_category`).
        The remaining excess is removed with :meth:`Trade.cap_net`, which re-balances globally
        by reducing the exports of the other regions, and warned about.

        ``demand`` must carry all trade dimensions; additional dimensions (e.g. the element
        dimension 'e') are summed away.
        """
        imp = trade.imports

        # align demand to historical time 'h', then drop element / other non-trade dims
        if "t" in demand.dims and "h" in imp.dims:
            demand = demand[{"t": imp.dims["h"]}]
        assert set(imp.dims.letters) <= set(demand.dims.letters), (
            f"'{trade.name or 'trade'}': demand must carry all trade dimensions; trade has "
            f"'{imp.dims.string}', demand has '{demand.dims.string}'."
        )
        demand = demand.sum_to(imp.dims.letters).maximum(0)

        if category_dim:
            self._reassign_net_imports_within_category(trade, demand, category_dim)

        self._cap_net_trade(trade, limit=demand, direction="imports", warn=True)

    @staticmethod
    def _reassign_net_imports_within_category(
        trade: Trade, demand: fd.FlodymArray, category_dim: str
    ):
        """Reassign net imports exceeding demand to sibling categories, on both trade sides.

        A region's excess of net imports over demand is moved to the categories that share all
        *other* dimensions (for plastics: the polymers of the same polymer type), as far as they
        still have headroom (demand - net imports). The part that does not fit is left for the
        cap.

        Moving imports between categories changes the global imports per category, while the
        changes cancel within each group. To keep the trade balanced, the exports are moved in
        the same way: the exports of categories whose global imports decrease are reduced in the
        regions that are net exporters of them, proportionally to their net exports, and these
        regions export the same amount of the categories whose global imports increase instead.
        A net exporter thus exports at most its net exports less, so it cannot become a net
        importer, and its exports per group stay unchanged.

        Args:
            trade (Trade): Trade to modify in place. Assumed to be globally balanced.
            demand (fd.FlodymArray): Domestic demand on the trade dimensions.
            category_dim (str): Letter of the dimension to reassign within.
        """
        eps = sys.float_info.epsilon
        net = trade.net_imports
        excess = (net - demand).maximum(0)
        headroom = (demand - net).maximum(0)
        excess_group = excess.sum_over(category_dim)
        headroom_group = headroom.sum_over(category_dim)
        # move as much of the excess as the group's headroom allows, the rest is capped later
        reassigned_group = excess_group.minimum(headroom_group)
        removed = excess * (reassigned_group / excess_group.maximum(eps))
        fill = headroom * (reassigned_group / headroom_group.maximum(eps))
        trade.imports[...] = (trade.imports - removed + fill).maximum(0)

        # global change of imports per category, which sums to zero within each group
        import_change = (fill - removed).sum_over("r")
        import_decrease = (-import_change).maximum(0)
        import_increase = import_change.maximum(0)
        positive_net_exports = (-net).maximum(0)
        export_decrease = positive_net_exports * (
            import_decrease / positive_net_exports.sum_over("r").maximum(eps)
        ).minimum(1)
        increase_share = import_increase / import_increase.sum_over(category_dim).maximum(eps)
        export_increase = export_decrease.sum_over(category_dim) * increase_share
        trade.exports[...] = (trade.exports - export_decrease + export_increase).maximum(0)

    def _warn_historical_net_trade_cap(
        self,
        trade_name: str,
        excess: fd.FlodymArray,
        total: fd.FlodymArray,
        tolerance: float,
        eps: float,
        direction: Literal["imports", "exports"],
    ):
        """Emit a detailed warning listing where historical net imports/exports were capped.

        Groups the affected coordinates by region and reports category breakdown plus affected
        years. Works for any dimension set: ``excess`` may be as small as ``(h, r)`` (no category
        dims) or carry extra dims such as ``(h, r, p, m)``.

        ``direction`` is ``"imports"`` or ``"exports"`` and selects the wording of the warning.
        """
        target = {"imports": "demand", "exports": "supply"}[direction]

        coords = excess.items_where(lambda x: x > tolerance)
        letters = excess.dims.letters
        t_letter = "h" if "h" in letters else "t"
        h_idx = letters.index(t_letter)
        r_idx = letters.index("r")
        extra_idx = [i for i, letter in enumerate(letters) if letter not in (t_letter, "r")]
        by_region = {}
        for row in coords:
            cats, years = by_region.setdefault(str(row[r_idx]), (set(), set()))
            if extra_idx:
                cats.add(", ".join(str(row[i]) for i in extra_idx))
            years.add(int(row[h_idx]))
        detail_lines = []
        for region, (cats, years) in sorted(by_region.items()):
            year_str = ", ".join(str(y) for y in sorted(years))
            if cats:
                detail_lines.append(f"    {region}: {'; '.join(sorted(cats))}; {year_str}")
            else:
                detail_lines.append(f"    {region}: {year_str}")
        detail = "\n".join(detail_lines)
        sum_dims = (t_letter, "r")
        max_reduction = np.max(
            (excess.sum_to(sum_dims) / total.maximum(0).sum_to(sum_dims).maximum(eps)).values
        )
        logging.warning(
            f"'{trade_name}' trade: historical net {direction} exceed domestic {target}; "
            f"capped {len(coords)} entries in {len(by_region)} regions. "
            f"Net {direction} reduced by up to {max_reduction:.0%} in a single region and year "
            f"to match {target}. Enable logging.DEBUG to see affected regions."
        )
        logging.debug(f"Affected regions and categories:\n{detail}")

    def get_historical_use_inflow_by_trade_adjusted_split(
        self,
        trade_name: str,
        supply: fd.FlodymArray,
        split: fd.FlodymArray,
        split_dims: tuple,
    ) -> fd.FlodymArray:
        """Distribute the ``manufactured_products_market => use`` flow among the split categories (end use, and
        for plastics also polymers).
        Where possible, this is done by the end-use split parameter ``split`` (already indexed
        to the historical time axis by the caller). However, the trade may be larger than the
        flow for a single split category. The other categories' inflow to the in-use stock
        must be reduced by these excess imports.

        ``split_dims`` are the category dimensions the split distributes over (e.g. ``("u",)``
        for steel, ``("u", "p")`` for plastics). Only called by the historical MFA systems.
        """
        # fmt: off
        net_imports = self.trade_set[trade_name].net_imports
        total_use_inflow = supply + net_imports
        use_inflow_target = total_use_inflow * split
        min_imports = net_imports.maximum(0)
        # imports exceeding the target values determined by the end-use split for each category
        imports_excess_total = (min_imports - use_inflow_target).maximum(0).sum_over(split_dims)
        # remainder of the target values not covered by imports, which should be covered by domestic manufacturing
        manufacturing_domestic_excess = (use_inflow_target - min_imports).maximum(0)
        manufacturing_domestic_excess_total = manufacturing_domestic_excess.sum_over(split_dims)
        # scale down such that the sum of the domestic manufacturing is reduced by the sum of the excess imports
        # i.e. domestic manufacturing for those categories where the target consumption exceeds imports
        # is reduced by the factor that imports exceed the target consumption for the other categories
        manufacturing_domestic = manufacturing_domestic_excess * (manufacturing_domestic_excess_total - imports_excess_total) / manufacturing_domestic_excess_total.maximum(sys.float_info.epsilon)
        # fmt: on
        return min_imports + manufacturing_domestic
