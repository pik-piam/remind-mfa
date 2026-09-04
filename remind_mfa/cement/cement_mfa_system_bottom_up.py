import flodym as fd

from remind_mfa.cement.cement_mfa_system_future import StockDrivenCementMFASystem
from remind_mfa.common.trade import TradeSet
from remind_mfa.common.data_blending import CriticallyDampedBlender


def expand_common_to_bu(arr: fd.FlodymArray, prm: dict[str, fd.FlodymArray]) -> fd.FlodymArray:
    """Expand an extensive common-end-use (c: Res/Com) quantity to bottom-up end uses
    (b: RS/RM/Com): residential values are split into single- (RS) and multi-family (RM)
    homes via the dwelling split; Com passes through.
    The dwelling split always sums to 1; `get_shares_over` re-asserts this to signal to
    the reconciliation optimizer that changing the sum has no effect.
    """
    dwelling_shares = prm["dwelling_split"].get_shares_over(("d",))
    bu_end_use_dim = prm["structure_split"].dims["b"]
    out = fd.FlodymArray(dims=arr.dims.replace("c", bu_end_use_dim))
    out[{"b": "RS"}] = arr[{"c": "Res"}] * dwelling_shares[{"d": "RS"}]
    out[{"b": "RM"}] = arr[{"c": "Res"}] * dwelling_shares[{"d": "RM"}]
    out[{"b": "Com"}] = arr[{"c": "Com"}]
    return out


def aggregate_bu_to_common(arr: fd.FlodymArray, common_end_use_dim: fd.Dimension) -> fd.FlodymArray:
    """Aggregate an extensive bottom-up-end-use (b) quantity to common end uses (c):
    Res = RS + RM."""
    out = fd.FlodymArray(dims=arr.dims.replace("b", common_end_use_dim))
    out[{"c": "Res"}] = arr[{"b": "RS"}] + arr[{"b": "RM"}]
    out[{"c": "Com"}] = arr[{"b": "Com"}]
    return out


def aggregate_bu_to_common_intensive[T: fd.FlodymArray](
    arr: T, common_end_use_dim: fd.Dimension
) -> T:
    """Aggregate an intensive bottom-up-end-use (b) quantity to common end uses (c): the
    residential value is the (identical) RS/RM value, Com passes through. Intensive
    twin of `aggregate_bu_to_common`. Class (e.g. Parameter) and name of the input are
    preserved."""
    out = type(arr)(dims=arr.dims.replace("b", common_end_use_dim), name=arr.name)
    out[{"c": "Res"}] = arr[{"b": "RS"}]
    out[{"c": "Com"}] = arr[{"b": "Com"}]
    return out


def extend_end_use_intensive[T: fd.FlodymArray](arr: T, extended_end_use_dim: fd.Dimension) -> T:
    """Extend an intensive end-use-resolved (u) quantity to extended end uses (e) by copying
    the residential value to both dwelling types (RS, RM). Only valid for intensive
    quantities (e.g. lifetimes); extensive quantities require a weighted split instead.
    Class (e.g. Parameter) and name of the input are preserved.
    """
    out = type(arr)(dims=arr.dims.replace("u", extended_end_use_dim), name=arr.name)
    out[{"e": "RS"}] = arr[{"u": "Res"}]
    out[{"e": "RM"}] = arr[{"u": "Res"}]
    for item in ("Com", "Ind", "Civ"):
        out[{"e": item}] = arr[{"u": item}]
    return out


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
        1. Compute the floorspace inflow (both historical and future) from the floorspace
           stock (common end uses c).
        2. Apply the dwelling split, structure split and MI to the floorspace inflow and
           calculate the inflow-driven DSM to get the bottom-up concrete stock (b, s).
        3. Extend the td inflow (from `td_in_use`, end uses u) to extended end uses and
           structures (e, s) and calculate the inflow-driven DSM to get the extended td stock.
        4. Blend historic td into future bu stock for the end uses the bottom-up model
           resolves (b); Ind, Civ and mortar stay td.
        5. Compute the complete MFA with the blended stock and historic trade.
        """

        self.compute_floorspace_stock()
        self.compute_bottom_up_stock()
        self.extend_top_down_stock(td_in_use)
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

    def compute_bottom_up_stock(self) -> fd.FlodymArray:
        """Resolve the floorspace inflow by bottom-up end use and structure and calculate
        the bu concrete stock (inflow-driven), assuming a constant split/MI over time.
        """
        stk = self.stocks

        stk["bu_in_use"].inflow[...] = self.concrete_from_floorspace(
            stk["floorspace"].inflow, self.parameters
        )
        self._set_lifetime("bu_in_use")
        stk["bu_in_use"].compute()
        return stk["bu_in_use"].stock

    def extend_top_down_stock(self, td_in_use: fd.Stock):
        """Resolve the top-down in-use stock (end uses u) into extended end uses (e) and
        structures (s): extend the td inflow and recalculate the td stock
        (inflow-driven). Equivalent to floorspace approach. Necessary to translate
        inflow splits into stock splits.
        Residential concrete is split into dwelling types and structures by joint
        MI-weighted mass shares (see `_concrete_mass_shares`); Com concrete is split
        over structures only. Ind, Civ and all mortar carry no structural resolution
        and are assigned to the unspecified structure U; residential mortar is split
        into dwelling types by floor area.
        """
        stk = self.stocks
        inflow = stk["td_in_use"].inflow

        td_inflow = td_in_use.inflow.sum_over("k")
        concrete = td_inflow[{"m": "concrete"}]
        mortar = td_inflow[{"m": "mortar"}]

        # concrete: split Res into dwellings by MI weighted floor area
        # introduce structure dimension to Res/Com by MI weighted floor area, assign U to Ind/Civ
        mass_split = self._concrete_mass_shares()
        inflow[{"m": "concrete", "e": "RS"}] = concrete[{"u": "Res"}] * mass_split[{"b": "RS"}]
        inflow[{"m": "concrete", "e": "RM"}] = concrete[{"u": "Res"}] * mass_split[{"b": "RM"}]
        inflow[{"m": "concrete", "e": "Com"}] = concrete[{"u": "Com"}] * mass_split[{"b": "Com"}]
        for item in ("Ind", "Civ"):
            inflow[{"m": "concrete", "e": item, "s": "U"}] = concrete[{"u": item}]

        # mortar: split Res into dwelling types by floor area
        # assign U (unspecified) structure dimension to all end uses
        inflow[{"m": "mortar", "e": "RS", "s": "U"}] = (
            mortar[{"u": "Res"}] * self.parameters["dwelling_split"][{"d": "RS"}]
        )
        inflow[{"m": "mortar", "e": "RM", "s": "U"}] = (
            mortar[{"u": "Res"}] * self.parameters["dwelling_split"][{"d": "RM"}]
        )
        for item in ("Com", "Ind", "Civ"):
            inflow[{"m": "mortar", "e": item, "s": "U"}] = mortar[{"u": item}]

        self._set_lifetime("td_in_use")
        stk["td_in_use"].compute()

    def _concrete_mass_shares(self) -> fd.FlodymArray:
        """Distributes the concrete mass of each top-down end use (u) over bottom-up end uses
        (b) and structures (s).
        First, floor-area shares are derived from the dwelling and structure splits.
        These are then reweighted by the relative MI of each category: categories with
        higher MI than the floor-area-weighted average for their parent end use receive a
        larger mass share, and vice versa.
        """
        prm = self.parameters
        dwelling_split = expand_common_to_bu(
            fd.FlodymArray.full(dims=self.dims["r", "c"], fill_value=1.0), prm
        )
        floor_area_split = dwelling_split * prm["structure_split"]  # (r, b, s)
        mi = prm["concrete_building_mi"]  # (r, b, s)

        # floor-area-weighted average MI per parent end use (Res pools RS + RM)
        avg_mi_per_end_use = aggregate_bu_to_common(
            (floor_area_split * mi).sum_over("s"), self.dims["c"]
        )
        avg_mi = fd.FlodymArray(dims=floor_area_split.dims.drop("s"))
        avg_mi[{"b": "RS"}] = avg_mi_per_end_use[{"c": "Res"}]
        avg_mi[{"b": "RM"}] = avg_mi_per_end_use[{"c": "Res"}]
        avg_mi[{"b": "Com"}] = avg_mi_per_end_use[{"c": "Com"}]

        return floor_area_split * mi / avg_mi

    def blend_stocks(self) -> fd.FlodymArray:
        """Combine the bu and td stocks into one:
        Blend smoothly between historic td and future bu concrete stock for the end uses
        the bottom-up model resolves (b: RS/RM/Com); Ind, Civ and all mortar stay td.
        """
        stk = self.stocks
        td_stock_expanded = stk["td_in_use"].stock

        # restrict the td stock to the bottom-up-resolved end uses
        bu_mask = {"e": self.dims["b"]}
        reduced_td_stock = td_stock_expanded[
            {
                **bu_mask,
                "m": "concrete",
                "t": self.dims["h"],
            }
        ]

        # Lifetime independent blend
        blender = CriticallyDampedBlender(
            time=self.dims["t"].items,
            historical=reduced_td_stock.values,
            prediction=stk["bu_in_use"].stock.values,
        )
        blended_stock = fd.FlodymArray.full_like(
            other=stk["bu_in_use"].stock,
            fill_value=blender.blend(),
        )

        combined_stock = td_stock_expanded.copy()
        combined_stock[{**bu_mask, "m": "concrete"}] = blended_stock
        return combined_stock

    def _set_lifetime(self, stock_name: str):
        """Set the stock's lifetime from the extended-end-use (e) lifetime parameters,
        restricted to the stock's own end-use resolution (detected from its dimensions):
        b-stocks slice e to b; c-stocks slice to b then average RS/RM to Res;
        e-stocks use the full extended end use directly."""
        mean = self.parameters["lifetime_mean"]
        std = self.parameters["lifetime_std"]
        letters = self.stocks[stock_name].dims.letters
        if "b" in letters:
            mean = mean[{"e": self.dims["b"]}]
            std = std[{"e": self.dims["b"]}]
        elif "c" in letters:
            mean = aggregate_bu_to_common_intensive(mean[{"e": self.dims["b"]}], self.dims["c"])
            std = aggregate_bu_to_common_intensive(std[{"e": self.dims["b"]}], self.dims["c"])
        self.stocks[stock_name].lifetime_model.set_prms(mean=mean, std=std)

    @staticmethod
    def concrete_from_floorspace(
        floorspace: fd.FlodymArray, prm: dict[str, fd.FlodymArray]
    ) -> fd.FlodymArray:
        """Concrete quantity (stock or inflow) from a floorspace quantity (resolved by
        common end use c), resolved by bottom-up end use (b) and structure (s).
        The splits always sum to 1; `get_shares_over` re-asserts this to signal to the
        reconciliation optimizer that changing the sum has no effect.
        """
        floorspace_bu = expand_common_to_bu(floorspace, prm)
        structure_shares = prm["structure_split"].get_shares_over(("s",))
        concrete = floorspace_bu * structure_shares * prm["concrete_building_mi"]
        # scale up building stock to account for hibernating (unused) stock
        total_concrete = concrete / (1.0 - prm["hibernating_stock_share"])
        return total_concrete
