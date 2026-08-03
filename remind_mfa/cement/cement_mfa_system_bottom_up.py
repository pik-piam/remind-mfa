import flodym as fd

from remind_mfa.cement.cement_mfa_system_future import StockDrivenCementMFASystem
from remind_mfa.common.trade import TradeSet
from remind_mfa.common.data_blending import CriticallyDampedBlender


def expand_common_to_bu(arr: fd.FlodymArray, prm: dict[str, fd.FlodymArray]) -> fd.FlodymArray:
    """Expand an extensive common-good (u: Res/Com) quantity to bottom-up goods
    (b: RS/RM/Com): residential values are split into single- (RS) and multi-family (RM)
    homes via the dwelling split; Com passes through.
    The dwelling split always sums to 1; `get_shares_over` re-asserts this to signal to
    the reconciliation optimizer that changing the sum has no effect.
    """
    dwelling_shares = prm["dwelling_split"].get_shares_over(("d",))
    bu_good_dim = prm["structure_split"].dims["b"]
    out = fd.FlodymArray(dims=arr.dims.replace("u", bu_good_dim))
    out[{"b": "RS"}] = arr[{"u": "Res"}] * dwelling_shares[{"d": "RS"}]
    out[{"b": "RM"}] = arr[{"u": "Res"}] * dwelling_shares[{"d": "RM"}]
    out[{"b": "Com"}] = arr[{"u": "Com"}]
    return out


def aggregate_bu_to_common(arr: fd.FlodymArray, common_good_dim: fd.Dimension) -> fd.FlodymArray:
    """Aggregate an extensive bottom-up-good (b) quantity to common goods (u):
    Res = RS + RM."""
    out = fd.FlodymArray(dims=arr.dims.replace("b", common_good_dim))
    out[{"u": "Res"}] = arr[{"b": "RS"}] + arr[{"b": "RM"}]
    out[{"u": "Com"}] = arr[{"b": "Com"}]
    return out


def aggregate_bu_to_common_intensive(
    arr: fd.FlodymArray, common_good_dim: fd.Dimension
) -> fd.FlodymArray:
    """Aggregate an intensive bottom-up-good (b) quantity to common goods (u): the
    residential value is the (identical) RS/RM value, Com passes through. Intensive
    twin of `aggregate_bu_to_common` (which sums); valid because RS and RM carry the
    same value for the intensive quantities this is used for (e.g. lifetimes)."""
    out = type(arr)(dims=arr.dims.replace("b", common_good_dim), name=arr.name)
    out[{"u": "Res"}] = arr[{"b": "RS"}]
    out[{"u": "Com"}] = arr[{"b": "Com"}]
    return out


def extend_good_intensive(arr: fd.FlodymArray, extended_good_dim: fd.Dimension) -> fd.FlodymArray:
    """Extend an intensive good-resolved (g) quantity to extended goods (e) by copying
    the residential value to both dwelling types (RS, RM). Only valid for intensive
    quantities (e.g. lifetimes); extensive quantities require a weighted split instead.
    Class (e.g. Parameter) and name of the input are preserved.
    """
    out = type(arr)(dims=arr.dims.replace("g", extended_good_dim), name=arr.name)
    out[{"e": "RS"}] = arr[{"g": "Res"}]
    out[{"e": "RM"}] = arr[{"g": "Res"}]
    for item in ("Com", "Ind", "Civ"):
        out[{"e": item}] = arr[{"g": item}]
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
           stock (common goods u).
        2. Apply the dwelling split, structure split and MI to the floorspace inflow and
           calculate the inflow-driven DSM to get the bottom-up concrete stock (b, s).
        3. Extend the td inflow (from `td_in_use`, goods g) to extended goods and
           structures (e, s) and calculate the inflow-driven DSM to get the extended td stock.
        4. Blend historic td into future bu stock for the goods the bottom-up model
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
        """Resolve the floorspace inflow by bottom-up good and structure and calculate
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
        """Resolve the top-down in-use stock (goods g) into extended goods (e) and
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
        inflow[{"m": "concrete", "e": "RS"}] = concrete[{"g": "Res"}] * mass_split[{"b": "RS"}]
        inflow[{"m": "concrete", "e": "RM"}] = concrete[{"g": "Res"}] * mass_split[{"b": "RM"}]
        inflow[{"m": "concrete", "e": "Com"}] = concrete[{"g": "Com"}] * mass_split[{"b": "Com"}]
        for item in ("Ind", "Civ"):
            inflow[{"m": "concrete", "e": item, "s": "U"}] = concrete[{"g": item}]

        # mortar: split Res into dwelling types by floor area
        # assign U (unspecified) structure dimension to all goods
        inflow[{"m": "mortar", "e": "RS", "s": "U"}] = (
            mortar[{"g": "Res"}] * self.parameters["dwelling_split"][{"d": "RS"}]
        )
        inflow[{"m": "mortar", "e": "RM", "s": "U"}] = (
            mortar[{"g": "Res"}] * self.parameters["dwelling_split"][{"d": "RM"}]
        )
        for item in ("Com", "Ind", "Civ"):
            inflow[{"m": "mortar", "e": item, "s": "U"}] = mortar[{"g": item}]

        self._set_lifetime("td_in_use")
        stk["td_in_use"].compute()

    def _concrete_mass_shares(self) -> fd.FlodymArray:
        """Distributes the concrete mass of each top-down good (g) over bottom-up goods
        (b) and structures (s).
        First, floor-area shares are derived from the dwelling and structure splits.
        These are then reweighted by the relative MI of each category: categories with
        higher MI than the floor-area-weighted average for their parent good receive a
        larger mass share, and vice versa.
        """
        prm = self.parameters
        dwelling_split = expand_common_to_bu(
            fd.FlodymArray.full(dims=self.dims["r", "u"], fill_value=1.0), prm
        )
        floor_area_split = dwelling_split * prm["structure_split"]  # (r, b, s)
        mi = prm["concrete_building_mi"]  # (r, b, s)

        # floor-area-weighted average MI per parent good (Res pools RS + RM)
        avg_mi_per_good = aggregate_bu_to_common(
            (floor_area_split * mi).sum_over("s"), self.dims["u"]
        )
        avg_mi = fd.FlodymArray(dims=floor_area_split.dims.drop("s"))
        avg_mi[{"b": "RS"}] = avg_mi_per_good[{"u": "Res"}]
        avg_mi[{"b": "RM"}] = avg_mi_per_good[{"u": "Res"}]
        avg_mi[{"b": "Com"}] = avg_mi_per_good[{"u": "Com"}]

        return floor_area_split * mi / avg_mi

    def blend_stocks(self) -> fd.FlodymArray:
        """Combine the bu and td stocks into one:
        Blend smoothly between historic td and future bu concrete stock for the goods
        the bottom-up model resolves (b: RS/RM/Com); Ind, Civ and all mortar stay td.
        """
        stk = self.stocks
        td_stock_expanded = stk["td_in_use"].stock

        # restrict the td stock to the bottom-up-resolved goods
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
        """Set the stock's lifetime from the extended-good (e) lifetime parameters,
        restricted to the stock's own good resolution (detected from its dimensions):
        b-stocks slice e to b; u-stocks slice to b then average RS/RM to Res;
        e-stocks use the full extended good directly."""
        mean = self.parameters["lifetime_mean"]
        std = self.parameters["lifetime_std"]
        letters = self.stocks[stock_name].dims.letters
        if "b" in letters:
            mean = mean[{"e": self.dims["b"]}]
            std = std[{"e": self.dims["b"]}]
        elif "u" in letters:
            mean = aggregate_bu_to_common_intensive(mean[{"e": self.dims["b"]}], self.dims["u"])
            std = aggregate_bu_to_common_intensive(std[{"e": self.dims["b"]}], self.dims["u"])
        self.stocks[stock_name].lifetime_model.set_prms(mean=mean, std=std)

    @staticmethod
    def concrete_from_floorspace(
        floorspace: fd.FlodymArray, prm: dict[str, fd.FlodymArray]
    ) -> fd.FlodymArray:
        """Concrete quantity (stock or inflow) from a floorspace quantity (resolved by
        common good u), resolved by bottom-up good (b) and structure (s).
        The splits always sum to 1; `get_shares_over` re-asserts this to signal to the
        reconciliation optimizer that changing the sum has no effect.
        """
        floorspace_bu = expand_common_to_bu(floorspace, prm)
        structure_shares = prm["structure_split"].get_shares_over(("s",))
        concrete = floorspace_bu * structure_shares * prm["concrete_building_mi"]
        # scale up building stock to account for hibernating (unused) stock
        total_concrete = concrete / (1.0 - prm["hibernating_stock_share"])
        return total_concrete
