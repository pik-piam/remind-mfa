import flodym as fd

from remind_mfa.cement.cement_mfa_system_future import StockDrivenCementMFASystem
from remind_mfa.common.trade import TradeSet
from remind_mfa.common.data_blending import CriticallyDampedBlender


def expand_common_to_bu(arr: fd.FlodymArray, prm: dict[str, fd.FlodymArray]) -> fd.FlodymArray:
    """Expand an extensive common-end-use (c: Residential/Commercial) quantity to bottom-up
    end uses (b: Residential Single-/Multi-Family, Commercial): residential values are split
    into single- and multi-family homes via the residential type split; Commercial passes through.
    The residential type split always sums to 1; `get_shares_over` re-asserts this to signal to
    the reconciliation optimizer that changing the sum has no effect.
    """
    residential_type_shares = prm["residential_type_split"].get_shares_over(("d",))
    bu_end_use_dim = prm["structure_split"].dims["b"]
    out = fd.FlodymArray(dims=arr.dims.replace("c", bu_end_use_dim))
    out[{"b": "Residential Single-Family"}] = (
        arr[{"c": "Residential"}] * residential_type_shares[{"d": "Residential Single-Family"}]
    )
    out[{"b": "Residential Multi-Family"}] = (
        arr[{"c": "Residential"}] * residential_type_shares[{"d": "Residential Multi-Family"}]
    )
    out[{"b": "Commercial"}] = arr[{"c": "Commercial"}]
    return out


def aggregate_bu_to_common(arr: fd.FlodymArray, common_end_use_dim: fd.Dimension) -> fd.FlodymArray:
    """Aggregate an extensive bottom-up-end-use (b) quantity to common end uses (c):
    Residential = Residential Single-Family + Residential Multi-Family."""
    out = fd.FlodymArray(dims=arr.dims.replace("b", common_end_use_dim))
    out[{"c": "Residential"}] = (
        arr[{"b": "Residential Single-Family"}] + arr[{"b": "Residential Multi-Family"}]
    )
    out[{"c": "Commercial"}] = arr[{"b": "Commercial"}]
    return out


def aggregate_bu_to_common_intensive[T: fd.FlodymArray](
    arr: T, common_end_use_dim: fd.Dimension
) -> T:
    """Aggregate an intensive bottom-up-end-use (b) quantity to common end uses (c): the
    residential value is the (identical) single-/multi-family value, Commercial passes
    through. Intensive twin of `aggregate_bu_to_common`. Class (e.g. Parameter) and name
    of the input are preserved."""
    out = type(arr)(dims=arr.dims.replace("b", common_end_use_dim), name=arr.name)
    out[{"c": "Residential"}] = arr[{"b": "Residential Single-Family"}]
    out[{"c": "Commercial"}] = arr[{"b": "Commercial"}]
    return out


def extend_end_use_intensive[T: fd.FlodymArray](arr: T, extended_end_use_dim: fd.Dimension) -> T:
    """Extend an intensive end-use-resolved (u) quantity to extended end uses (e) by copying
    the residential value to both residential types (single- and multi-family). Only valid
    for intensive quantities (e.g. lifetimes); extensive quantities require a weighted split
    instead.
    Class (e.g. Parameter) and name of the input are preserved.
    """
    out = type(arr)(dims=arr.dims.replace("u", extended_end_use_dim), name=arr.name)
    out[{"e": "Residential Single-Family"}] = arr[{"u": "Residential"}]
    out[{"e": "Residential Multi-Family"}] = arr[{"u": "Residential"}]
    for item in ("Commercial", "Industrial", "Civil Engineering"):
        out[{"e": item}] = arr[{"u": item}]
    return out


class StockDrivenBottomUpCementMFASystem(StockDrivenCementMFASystem):

    def compute(self, td_use: fd.Stock, historical_trade: TradeSet):
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
        2. Apply the residential type split, structure split and MI to the floorspace inflow and
           calculate the inflow-driven DSM to get the bottom-up concrete stock (b, s).
        3. Extend the td inflow (from `td_use`, end uses u) to extended end uses and
           structures (e, s) and calculate the inflow-driven DSM to get the extended td stock.
        4. Blend historical td into future bu stock for the end uses the bottom-up model
           resolves (b); Industrial, Civil Engineering and mortar stay td.
        5. Compute the complete MFA with the blended stock and historical trade.
        """

        self.compute_floorspace_stock()
        self.compute_bottom_up_stock()
        self.extend_top_down_stock(td_use)
        combined_stock = self.blend_stocks()
        super().compute(combined_stock, historical_trade)

    def compute_floorspace_stock(self):
        """Calculate the floorspace inflow from stock change + lifetime (stock-driven)."""
        prm = self.parameters
        stk = self.stocks

        stock = prm["floorspace"]  # TODO remove once mrmfa is fixed
        stock[{"t": [y for y in stock.dims["t"].items if y < 2000]}] = (
            0  # TODO remove once mrmfa is fixed
        )
        stk["floorspace"].stock = stock
        self.set_prms_and_compute(stk["floorspace"])

    def compute_bottom_up_stock(self) -> fd.FlodymArray:
        """Resolve the floorspace inflow by bottom-up end use and structure and calculate
        the bu concrete stock (inflow-driven), assuming a constant split/MI over time.
        """
        stk = self.stocks

        stk["bu_use"].inflow[...] = self.concrete_from_floorspace(
            stk["floorspace"].inflow, self.parameters
        )
        self.set_prms_and_compute(stk["bu_use"])
        return stk["bu_use"].stock

    def extend_top_down_stock(self, td_use: fd.Stock):
        """Resolve the top-down in-use stock (end uses u) into extended end uses (e) and
        structures (s): extend the td inflow and recalculate the td stock
        (inflow-driven). Equivalent to floorspace approach. Necessary to translate
        inflow splits into stock splits.
        Residential concrete is split into residential types and structures by joint
        MI-weighted mass shares (see `_concrete_mass_shares`); Commercial concrete is split
        over structures only. Industrial, Civil Engineering and all mortar carry no structural
        resolution and are assigned to the unspecified structure; residential mortar is split
        into residential types by floor area.
        """
        stk = self.stocks
        inflow = stk["td_use"].inflow

        td_inflow = td_use.inflow.sum_over("k")
        concrete = td_inflow[{"m": "Concrete"}]
        mortar = td_inflow[{"m": "Mortar"}]

        # concrete: split Residential into residential types by MI weighted floor area
        # introduce structure dimension to Residential/Commercial by MI weighted floor area,
        # assign unspecified structure to Industrial/Civil Engineering
        mass_split = self._concrete_mass_shares()
        inflow[{"m": "Concrete", "e": "Residential Single-Family"}] = (
            concrete[{"u": "Residential"}] * mass_split[{"b": "Residential Single-Family"}]
        )
        inflow[{"m": "Concrete", "e": "Residential Multi-Family"}] = (
            concrete[{"u": "Residential"}] * mass_split[{"b": "Residential Multi-Family"}]
        )
        inflow[{"m": "Concrete", "e": "Commercial"}] = (
            concrete[{"u": "Commercial"}] * mass_split[{"b": "Commercial"}]
        )
        for item in ("Industrial", "Civil Engineering"):
            inflow[{"m": "Concrete", "e": item, "s": "Unspecified Structure"}] = concrete[
                {"u": item}
            ]

        # mortar: split Residential into residential types by floor area
        # assign unspecified structure to all end uses
        res_type_split = self.parameters["residential_type_split"]
        inflow[{"m": "Mortar", "e": "Residential Single-Family", "s": "Unspecified Structure"}] = (
            mortar[{"u": "Residential"}] * res_type_split[{"d": "Residential Single-Family"}]
        )
        inflow[{"m": "Mortar", "e": "Residential Multi-Family", "s": "Unspecified Structure"}] = (
            mortar[{"u": "Residential"}] * res_type_split[{"d": "Residential Multi-Family"}]
        )
        for item in ("Commercial", "Industrial", "Civil Engineering"):
            inflow[{"m": "Mortar", "e": item, "s": "Unspecified Structure"}] = mortar[{"u": item}]

        self.set_prms_and_compute(stk["td_use"])

    def _concrete_mass_shares(self) -> fd.FlodymArray:
        """Distributes the concrete mass of each top-down end use (u) over bottom-up end uses
        (b) and structures (s).
        First, floor-area shares are derived from the residential type and structure splits.
        These are then reweighted by the relative MI of each category: categories with
        higher MI than the floor-area-weighted average for their parent end use receive a
        larger mass share, and vice versa.
        """
        prm = self.parameters
        residential_type_split = expand_common_to_bu(
            fd.FlodymArray.full(dims=self.dims["r", "c"], fill_value=1.0), prm
        )
        floor_area_split = residential_type_split * prm["structure_split"]  # (r, b, s)
        mi = prm["concrete_building_mi"]  # (r, b, s)

        # floor-area-weighted average MI per parent end use (Residential pools both
        # residential types)
        avg_mi_per_end_use = aggregate_bu_to_common(
            (floor_area_split * mi).sum_over("s"), self.dims["c"]
        )
        avg_mi = fd.FlodymArray(dims=floor_area_split.dims.drop("s"))
        avg_mi[{"b": "Residential Single-Family"}] = avg_mi_per_end_use[{"c": "Residential"}]
        avg_mi[{"b": "Residential Multi-Family"}] = avg_mi_per_end_use[{"c": "Residential"}]
        avg_mi[{"b": "Commercial"}] = avg_mi_per_end_use[{"c": "Commercial"}]

        return floor_area_split * mi / avg_mi

    def blend_stocks(self) -> fd.FlodymArray:
        """Combine the bu and td stocks into one:
        Blend smoothly between historical td and future bu concrete stock for the end uses
        the bottom-up model resolves (b); Industrial, Civil Engineering and all mortar stay td.
        """
        stk = self.stocks
        td_stock_expanded = stk["td_use"].stock

        # restrict the td stock to the bottom-up-resolved end uses
        bu_mask = {"e": self.dims["b"]}
        reduced_td_stock = td_stock_expanded[
            {
                **bu_mask,
                "m": "Concrete",
                "t": self.dims["h"],
            }
        ]

        # Lifetime independent blend
        blender = CriticallyDampedBlender(
            time=self.dims["t"].items,
            historical=reduced_td_stock.values,
            prediction=stk["bu_use"].stock.values,
        )
        blended_stock = fd.FlodymArray.full_like(
            other=stk["bu_use"].stock,
            fill_value=blender.blend(),
        )

        combined_stock = td_stock_expanded.copy()
        combined_stock[{**bu_mask, "m": "Concrete"}] = blended_stock
        return combined_stock

    def set_prms_and_compute(self, stock: fd.DynamicStockModel):
        """Set the lifetime model parameters and compute the stock.

        The extended-end-use (e) lifetime parameters are restricted to the stock's own
        end-use resolution (detected from its dimensions): b-stocks slice e to b; c-stocks
        slice to b then aggregate the residential types to Residential; e-stocks use the
        full extended end use directly.

        Note: Overrides `CommonMFASystem.set_prms_and_compute` without calling `super()`,
        since the parent reads the parameters directly. Changes to the parent body must be
        mirrored here.

        Args:
            stock (fd.DynamicStockModel): Stock to set parameters for and compute.
        """
        letters = stock.dims.letters
        lifetime_prms = {}
        for name in (
            "lifetime_mean",
            "lifetime_std",
            "lifetime_factor_nurture",
            "lifetime_factor_cohort",
        ):
            prm = self.parameters[name]
            if "b" in letters:
                prm = prm[{"e": self.dims["b"]}]
            elif "c" in letters:
                prm = aggregate_bu_to_common_intensive(prm[{"e": self.dims["b"]}], self.dims["c"])
            lifetime_prms[name] = prm
        lifetime_model = stock.lifetime_model
        lifetime_model.n_pts_per_interval = self.lifetime_n_pts_per_interval
        lifetime_model.mean = lifetime_prms["lifetime_mean"]
        lifetime_model.std = lifetime_prms["lifetime_std"]
        lifetime_model.lt_factor_by_year = lifetime_prms["lifetime_factor_nurture"]
        lifetime_model.lt_factor_by_cohort = lifetime_prms["lifetime_factor_cohort"]
        stock.compute()

    @staticmethod
    def concrete_from_floorspace(
        floorspace: fd.FlodymArray, prm: dict[str, fd.FlodymArray]
    ) -> fd.FlodymArray:
        """Concrete quantity (stock or inflow) from a floorspace quantity (resolved by
        common end use c), resolved by bottom-up end use (b) and structure (s).
        The splits always sum to 1; `get_shares_over` re-asserts this to signal to the
        reconciliation optimizer that changing the sum has no effect.
        """
        # scale up occupied to total residential floorspace (vacant dwellings and second homes)
        total_floorspace = floorspace.copy()
        total_floorspace[{"c": "Residential"}] = floorspace[{"c": "Residential"}] / (
            1.0 - prm["unoccupied_residential_stock_share"]
        )
        floorspace_bu = expand_common_to_bu(total_floorspace, prm)
        structure_shares = prm["structure_split"].get_shares_over(("s",))
        concrete = floorspace_bu * structure_shares * prm["concrete_building_mi"]
        return concrete
