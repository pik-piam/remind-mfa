import logging
import sys
import numpy as np
import flodym as fd
from typing import Optional

from remind_mfa.common.trade import TradeSet
from remind_mfa.common.common_config import CommonCfg


class CommonMFASystem(fd.MFASystem):

    cfg: CommonCfg
    trade_set: Optional[TradeSet] = None

    def correct_negative_inflow(self, stock_name: str, warn_small_negative: bool = True):
        """After a StockDrivenDSM computation, correct any negative inflows.
        Recomputes the stock as InflowDrivenDSM with the corrected inflow.
        As some small negative inflows may have their origin in numerical issues,
        the corresponding warning can be suppressed with warn_small_negative=False.
        """
        stock = self.stocks[stock_name]
        min_inflow = stock.inflow.values.min()
        if min_inflow >= 0:
            return
        negative_regions = [r for r in self.dims["r"].items if stock.inflow[r].values.min() < 0]
        small_negative_threshold = 1e-6
        is_small = abs(min_inflow) <= small_negative_threshold
        if not is_small or warn_small_negative:
            logging.warning(
                f"In-use stock inflow <0 in regions {negative_regions}! Correcting negative inflow to 0."
            )
        corrected_inflow = stock.inflow.maximum(0)
        self.stocks[stock_name] = fd.InflowDrivenDSM(
            dims=stock.dims,
            lifetime_model=stock.lifetime_model,
            name=stock.name,
            process=stock.process,
        )
        self.stocks[stock_name].inflow[...] = corrected_inflow
        self.stocks[stock_name].compute()

    def fill_trade(self):
        """
        Fill trade from parameters named after the scheme [market_name]_imports and [market_name]_exports.
        """
        for name, trade in self.trade_set.markets.items():
            trade.imports[...] = self.parameters[f"{name}_imports"]
            trade.exports[...] = self.parameters[f"{name}_exports"]

    def cap_historical_net_exports_to_supply(self, trade_name: str, supply: fd.FlodymArray):
        """Cap a historic trade's *net* exports at the available domestic supply so downstream
        flows cannot go negative when historic net exports exceed domestic production, then
        re-balance globally. Gross exports may still exceed supply where they are covered by
        imports (stop-over / re-export trade), since fabrication inflow = supply + imports -
        exports only requires exports - imports <= supply.
        Net exports are calculated per dimension (type/material/good) and then summed up,
        because positive net imports (imports > exports) of one good cannot be balanced by
        re-exporting a different good, so that net amount is not stop-over trade and must be consumed.

        ``balance`` re-inflates the opposite (import) side and thereby partially reintroduces
        the violation, so the cap and balance are iterated to convergence.
        Warns with the region/category coordinates where net exports had to be reduced.

        Only called by the historic MFA systems.
        """
        trade = self.trade_set[trade_name]
        eps = sys.float_info.epsilon
        tolerance = 100 * self._absolute_float_precision
        # Compare net exports and supply on the dimensions they share. The trade may be more
        # granular than the supply (e.g. per-good indirect exports vs. total fabrication supply)
        # or coarser (e.g. aggregate scrap exports vs. per-good recovered scrap), so both are
        # summed to their common dimensions before capping.
        common_dims = tuple(
            letter for letter in trade.exports.dims.letters if letter in supply.dims.letters
        )
        supply_total = supply.sum_to(common_dims).maximum(0)
        for iteration in range(50):
            net_exports = (trade.exports - trade.imports).maximum(0)
            net_exports_total = net_exports.sum_to(common_dims)
            # sum of positive per-good net exports may not exceed domestic supply
            net_export_excess = (net_exports_total - supply_total).maximum(0)
            if not (net_export_excess.values > tolerance).any():
                break
            if iteration == 0:
                self._warn_historical_net_export_cap(
                    trade_name, net_export_excess, net_exports_total, tolerance, eps
                )
            # reduce exports of net-export goods to bring positive net exports down to supply,
            # keeping their imports (same-good stop-over) untouched; factor in [0, 1]
            export_factor = (net_exports_total - net_export_excess) / net_exports_total.maximum(eps)
            trade.exports[...] = trade.exports - net_exports * (1 - export_factor)
            trade.balance(to="minimum")
        else:
            logging.warning(
                f"'{trade_name}': positive-net-export cap did not converge after 50 iterations."
            )

    def _warn_historical_net_export_cap(
        self,
        trade_name: str,
        net_export_excess: fd.FlodymArray,
        net_exports_total: fd.FlodymArray,
        tolerance: float,
        eps: float,
    ):
        """Emit a detailed warning listing where historic net exports were capped at supply.

        Groups the affected coordinates by region and reports the remaining (non-time,
        non-region) category coordinates plus the affected years. Works for any dimension
        set: ``net_export_excess`` may be as small as ``(h, r)`` (no category dims) or
        carry extra dims such as ``(h, r, p, m)``.
        """
        coords = net_export_excess.items_where(lambda x: x > tolerance)
        letters = net_export_excess.dims.letters
        h_idx = letters.index("h")
        r_idx = letters.index("r")
        extra_idx = [i for i, letter in enumerate(letters) if letter not in ("h", "r")]
        # categories (extra dims) and years affected per region
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
        max_reduction = np.max(
            (
                net_export_excess.sum_to(("h", "r"))
                / net_exports_total.sum_to(("h", "r")).maximum(eps)
            ).values
        )
        logging.warning(
            f"'{trade_name}': historic net exports exceed available domestic supply; "
            f"scaled down {len(coords)} entries:\n{detail}"
            f"\nNet exports reduced by up to {max_reduction:.0%} in a single region and year "
            f"to cap them at domestic supply."
        )

    def get_historical_use_inflow_by_trade_adjusted_split(
        self,
        trade_name: str,
        supply: fd.FlodymArray,
        split: fd.FlodymArray,
        split_dims: tuple,
    ) -> fd.FlodymArray:
        """Distribute the ``good_market => use`` flow among the split categories (goods, and
        for plastics also materials).
        Where possible, this is done by the sector split parameter ``split`` (already indexed
        to the historic time axis by the caller). However, the trade may be larger than the
        flow for a single split category. The other categories' inflow to the in-use stock
        must be reduced by these excess imports.

        ``split_dims`` are the category dimensions the split distributes over (e.g. ``("g",)``
        for steel, ``("g", "m")`` for plastics). Only called by the historic MFA systems.
        """
        # fmt: off
        net_imports = self.trade_set[trade_name].net_imports
        total_use_inflow = supply + net_imports
        use_inflow_target = total_use_inflow * split
        min_imports = net_imports.maximum(0)
        # imports exceeding the target values determined by the sector split for each category
        imports_excess_total = (min_imports - use_inflow_target).maximum(0).sum_over(split_dims)
        # remainder of the target values not covered by imports, which should be covered by domestic fabrication
        fabrication_domestic_excess = (use_inflow_target - min_imports).maximum(0)
        fabrication_domestic_excess_total = fabrication_domestic_excess.sum_over(split_dims)
        # scale down such that the sum of the domestic fabrication is reduced by the sum of the excess imports
        # i.e. domestic fabrication for those categories where the target consumption exceeds imports
        # is reduced by the factor that imports exceed the target consumption for the other categories
        fabrication_domestic = fabrication_domestic_excess * (fabrication_domestic_excess_total - imports_excess_total) / fabrication_domestic_excess_total.maximum(sys.float_info.epsilon)
        # fmt: on
        return min_imports + fabrication_domestic
