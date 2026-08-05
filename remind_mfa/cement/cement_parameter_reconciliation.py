import numpy as np
from typing import Callable, Tuple, Optional
import flodym as fd
import logging
import itertools
import math
import random
from copy import deepcopy

from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.cement.cement_mfa_system_historic import InflowDrivenHistoricCementMFASystem
from remind_mfa.cement.cement_mfa_system_bottom_up import (
    StockDrivenBottomUpCementMFASystem,
    REDUCED_STOCK_TYPE,
)


class CementParameterReconciliation:
    """Reconcile parameters of the top-down (td) and bottom-up (bu) cement stock models.

    Both models predict the in-use concrete stock in residential and commercial buildings
    in the last historic year, but they disagree. This class nudges the uncertain input
    parameters just enough to make them agree, moving each parameter as little as its
    uncertainty allows.

    How it works:
        Each parameter x_p is scaled by a factor exp(d_p), so d_p is its correction in log
        space. We look for the corrections that make the two models agree while staying as
        small as possible, letting more uncertain parameters move more:

            minimize    sum_p (d_p / sigma_p)^2    small, uncertainty-weighted corrections
            subject to  log(td) = log(bu)          the two models agree

        where sigma_p is the relative uncertainty of parameter p. The constraint is
        non-linear in d_p, so we linearise it and repeat (Gauss-Newton). Each iteration
        measures

            r   = log(td / bu)                 the current mismatch
            S_p = d log(td/bu) / d log(x_p)    how much parameter p shifts the mismatch
                                               (the "sensitivity", via finite differences),

        turning the constraint into the linear ``r + sum_p S_p d_p = 0``, which has the
        closed-form (KKT) solution

            d_p = -sigma_p^2 * S_p^T lambda,
            (sum_p S_p sigma_p^2 S_p^T) lambda = r.

        In code: S_p = ``sensitivities[p]``, lambda = ``lmda``, r = ``residual_log``,
        sigma_p^2 = ``get_variances(p)``.

        Each iteration minimises that single step, not the total correction so far.
        Anchoring the penalty to the running total does not converge here: re-normalising
        the split parameters (see below) keeps undoing part of each correction, which an
        anchored objective would then re-request every iteration.

    Dimension handling:
        - The stock type dimension ``s`` is reduced to ``u`` (Res/Com), where top-down and
          bottom-up data overlap.
        - Each parameter receives one correction factor per element of its dimensions
          except time (``t``/``h``): corrections are constant across all time steps.
        - Split parameters are re-normalized to sum to 1 after each correction. Full splits
          (every dim item is covered in the reconciliation: function/structure) are scaled
          proportionally. Partial splits (only a subset of dim items covered: concrete for the
          material split, Res/Com for the stock-type split) keep their reconciled values and
          let the unused complement (mortar; Civ/Ind) absorb ``1 - sum(reconciled)``.
    """

    _normalization_dims: dict[str, tuple[str, ...]] = {
        "structure_buildings_split": ("Structure",),
        "function_buildings_split": ("Function",),
        "product_material_split": ("Product Material",),
        "stock_type_split": ("Stock Type",),
    }

    # Partial splits: only these dim items are part of the reconciliation.
    _reconciled_split_items: dict[str, tuple[str, ...]] = {
        "product_material_split": ("concrete",),
        "stock_type_split": tuple(REDUCED_STOCK_TYPE.items),
    }

    def __init__(
        self,
        ref_mfa: CommonMFASystem,
        output_dims_are_independent: bool = False,
    ):
        """
        Initialize the parameter reconciliation.

        Args:
            ref_mfa: The reference MFA system providing parameters, flows, stocks, and dimensions.
            output_dims_are_independent: If True, assumes that dimensions shared between a
                parameter and the reconciliation output are independent across their values
                (e.g., changing a parameter for region EU does not affect the output for Asia).
                This allows a more efficient block-diagonal Jacobian computation instead of
                building the full output × parameter matrix.
        """
        self.ref_mfa = ref_mfa
        self._year_of_reconciliation = ref_mfa.dims["h"].items[-1]

        # parameters will get one correction factor across all time steps.
        self._no_correction_dim_letters = ("t", "h")  # instead of df/dx, now calculating df/dd

        self.output_dims_are_independent = output_dims_are_independent

        self.prepare_dims()
        self.input_prms = deepcopy(ref_mfa.parameters)
        self.prepare_prms(ref_mfa.parameters)
        self.prepare_flws()
        self.prepare_stks()
        self.prepare_trds()
        self._rel_stds = self._build_rel_stds()

    def prepare_dims(self):
        dims = self.ref_mfa.dims
        self.input_dims = deepcopy(dims)
        self.dims = dims.replace("s", REDUCED_STOCK_TYPE)

    def prepare_prms(self, source_prms: dict[str, fd.Parameter]):
        """Build the reduced working parameters `prms` from `source_prms`, and the
        dimensions along which each parameter is corrected (`prms_adj_dims`)."""
        self.prms: dict[str, fd.Parameter] = {}
        self.prms_adj_dims: dict[str, fd.DimensionSet] = {}
        for key, val in source_prms.items():
            val = self.reduce_prm(key, val)
            self.prms[key] = val
            self.prms_adj_dims[key] = self.remove_fd_dims_if_present(
                val.dims, self._no_correction_dim_letters
            )

    def reduce_prm(self, prm_name: str, prm: fd.FlodymArray) -> fd.FlodymArray:
        """Reduce a parameter (or an array with the parameter's dims) to the dimensions
        used during reconciliation."""
        # reduce stock type dimension
        if "s" in prm.dims.letters:
            prm = prm[{"s": REDUCED_STOCK_TYPE}]
        # remove time dimension
        if prm_name in ["floorspace"]:
            prm = prm[{"t": self._year_of_reconciliation}]
        return prm

    def prepare_flws(self):
        self.flws: dict[str, fd.Flow] = {}
        for key, val in self.ref_mfa.flows.items():
            if "s" in val.dims.letters:
                val = val[{"s": REDUCED_STOCK_TYPE}]  # slicing returns a new array
            else:
                val = deepcopy(val)  # protect ref_mfa flows from in-place modification
            self.flws[key] = val

    def prepare_stks(self):
        self.stks: dict[str, fd.Stock] = {}
        for key, val in self.ref_mfa.stocks.items():
            val = deepcopy(val)
            if "s" in val.dims.letters:
                val.inflow = val.inflow[{"s": REDUCED_STOCK_TYPE}]
                val.outflow = val.outflow[{"s": REDUCED_STOCK_TYPE}]
                val.stock = val.stock[{"s": REDUCED_STOCK_TYPE}]
                val.dims = val.inflow.dims
                if hasattr(val, "lifetime_model"):
                    val.lifetime_model.dims = val.inflow.dims
            self.stks[key] = val

    def prepare_trds(self):
        """Leave trade as is."""
        self.trds = deepcopy(self.ref_mfa.trade_set)

    @staticmethod
    def remove_fd_dims_if_present(
        dims: fd.DimensionSet, letters_to_remove: Tuple
    ) -> fd.DimensionSet:
        new_dims = dims
        for letter in letters_to_remove:
            if letter in new_dims.letters:
                new_dims = new_dims.drop(letter)
        return new_dims

    def correct_parameters(
        self,
        max_iter: int = 1,
        tol: Optional[float] = None,
    ) -> dict[str, fd.Parameter]:
        """Iteratively correct parameters to reconcile top-down and bottom-up stocks.

        Each iteration linearises around the current working parameters, computes a
        constrained least-squares log-correction (see class docstring), and applies them.

        Args:
            max_iter: Maximum number of correction iterations.
            tol: Convergence tolerance.  Stop early when
                ``max(|log(td / bu)|) < tol``.  If *None*, always run
                ``max_iter`` iterations.

        Returns:
            The corrected parameters in their original dimensions.
        """
        self.output_prms = deepcopy(self.input_prms)

        for i in range(max_iter):
            td = self.calc_top_down_stock(self.prms)
            bu = self.calc_bottom_up_stock(self.prms)
            residual_log = self.calc_residual_log(td, bu)
            mismatch = self.mismatch_logging(
                residual_log, td, bu, label=f"iteration {i + 1}/{max_iter}"
            )

            if tol is not None and mismatch < tol:
                logging.info(
                    f"Converged after {i} iteration(s) (mismatch {mismatch:.4f} < tol {tol})."
                )
                return self.output_prms

            # fresh sensitivity matrices each iteration (re-linearise around current prms)
            sensitivities = self.compute_sensitivities(td, bu)
            lmda = self.solve_lagrange_multipliers(sensitivities, residual_log)
            corrections = self.calc_corrections(sensitivities, lmda)

            self.apply_corrections(corrections)
            # set output prms as new working prms
            self.prepare_prms(self.output_prms)

        # report the mismatch reached by the last applied corrections
        td = self.calc_top_down_stock(self.prms)
        bu = self.calc_bottom_up_stock(self.prms)
        self.mismatch_logging(self.calc_residual_log(td, bu), td, bu, label="final")

        return self.output_prms

    def calc_residual_log(self, td: fd.FlodymArray, bu: fd.FlodymArray) -> fd.FlodymArray:
        """Residual r = log(td / bu), with validity checks for the log-space treatment."""
        if td.dims.letters != bu.dims.letters:
            # this is important for later numpy-based calculations
            raise ValueError(
                "Top-down and bottom-up stocks must have the same dimension order, "
                f"got {td.dims.letters} and {bu.dims.letters}."
            )
        if np.any(td.values <= 0) or np.any(bu.values <= 0):
            raise ValueError(
                "Top-down and bottom-up stocks must be strictly positive "
                "for log-space reconciliation."
            )
        return td.apply(np.log) - bu.apply(np.log)

    @staticmethod
    def mismatch_logging(
        residual_log: fd.FlodymArray, td: fd.FlodymArray, bu: fd.FlodymArray, label: str
    ) -> float:
        mismatch = float(np.max(np.abs(residual_log.values)))
        percent_mismatch = float(np.max(np.abs(td.values - bu.values) / np.abs(bu.values)) * 100)
        logging.info(
            f"Reconciliation {label}: "
            f"max |log(td/bu)| = {mismatch:.4f}, "
            f"max percent mismatch = {percent_mismatch:.2f}%"
        )
        return mismatch

    def calc_top_down_stock(self, prm: dict[str, fd.FlodymArray]):
        """Top-down stock calculation for reconciliaton."""

        # 1. Compute product stock from hisoric MFA
        cement_stock = InflowDrivenHistoricCementMFASystem.compute_cement_stock(
            prm, self.trds, self.flws, self.stks
        )
        product_stock = cement_stock * prm["product_material_split"] / prm["cement_ratio"]

        # 2. Reduce dimensions to match bottom-up stock dimensions
        # 2.1 Use only reconciliation year
        product_stock = product_stock[{"h": self._year_of_reconciliation}]

        # 2.2 Use only the reconciled material (concrete) [no mortar]
        concrete_stock = product_stock[
            {"m": self._reconciled_split_items["product_material_split"][0]}
        ]

        return concrete_stock

    @staticmethod
    def calc_bottom_up_stock(prm: dict[str, fd.FlodymArray], stock_type_letter: str = "u"):
        """Bottom-up stock calculation for reconciliation."""
        # 1. Compute concrete stock bottom-up
        concrete_stk = StockDrivenBottomUpCementMFASystem.concrete_from_floorspace(
            prm["floorspace"], prm
        )

        # 2. Reduce dimensions to match top-down stock dimensions
        # 2.1 Remove building function
        reduced_cement_stock = fd.FlodymArray(dims=concrete_stk.dims.drop("f"))
        reduced_cement_stock[{stock_type_letter: "Res"}] = (
            concrete_stk[{"f": "RS", stock_type_letter: "Res"}]
            + concrete_stk[{"f": "RM", stock_type_letter: "Res"}]
        )
        reduced_cement_stock[{stock_type_letter: "Com"}] = concrete_stk[
            {"f": "Com", stock_type_letter: "Com"}
        ]

        # 2.2 Remove building structure
        return reduced_cement_stock.sum_over("b")

    def compute_sensitivities(
        self, td: fd.FlodymArray, bu: fd.FlodymArray
    ) -> dict[str, np.ndarray]:
        """Sensitivity matrices S_p of the residual log(td/bu) for all uncertain
        parameters used by either stock model."""
        sensitivities: dict[str, np.ndarray] = {}
        self.add_sensitivities(sensitivities, self.calc_top_down_stock, td, sign=1)
        self.add_sensitivities(sensitivities, self.calc_bottom_up_stock, bu, sign=-1)
        return sensitivities

    def add_sensitivities(
        self,
        sensitivities: dict[str, np.ndarray],
        f: Callable[[dict[str, fd.FlodymArray]], fd.FlodymArray],
        f0: fd.FlodymArray,
        sign: int,
    ):
        """
        Compute sensitivity matrices for parameters used in the given model function and
        add them to `sensitivities`. Matrices of parameters appearing in several model
        functions are summed.
        TODO Analytical sensitivities for parameters could be provided to reduce computation time.
        """
        relevant_params = self.get_relevant_parameters(f, self.prms)

        for prm_name in relevant_params:
            # zero uncertainty parameters do not need to be adjusted
            if not np.any(self.get_variances(prm_name)):
                continue
            S_mat = self.calc_sensitivity(f, f0, prm_name, sign=sign)
            if prm_name in sensitivities:
                logging.info(
                    f"Sensitivity for parameter {prm_name} already exists; summing matrices."
                )
                sensitivities[prm_name] = sensitivities[prm_name] + S_mat
            else:
                sensitivities[prm_name] = S_mat

    @staticmethod
    def get_relevant_parameters(model_func: Callable, prms: dict[str, fd.Parameter]) -> set:
        """
        Runs a model once to spy on which parameters are used.
        """
        # Wrap the parameters in a tracking dict
        spy_prms = DependencyTracker(prms)

        # Run the model
        _ = model_func(spy_prms)

        return spy_prms.accessed_keys

    def calc_sensitivity(
        self,
        f: Callable[[dict[str, fd.FlodymArray]], fd.FlodymArray],
        f0: fd.FlodymArray,
        prm_name: str,
        sign: int = 1,
    ) -> np.ndarray:
        """Log-log sensitivity S = d log(td/bu) / d log x_p as a 2D (output x parameter) matrix.

        `sign` is +1 if f contributes to the numerator (td), -1 for the denominator (bu), so
        that S for bu parameters is negated to give d log(td/bu) / d log x_p correctly.
        """
        J = self.calc_jacobian(f, f0, prm_name)

        if self.output_dims_are_independent:
            # Convert FlodymArray Jacobian to numpy matrix and scale for logarithmic sensitivity
            S = self.flodym_jacobian_to_matrix(J / f0, f0.dims, self.prms_adj_dims[prm_name])
        else:
            f0_flat = self.flatten_fd_to_np(f0)[:, np.newaxis]
            S = J / f0_flat

        return sign * S

    def calc_jacobian(
        self,
        f: Callable[[dict[str, fd.FlodymArray]], fd.FlodymArray],
        f0: fd.FlodymArray,
        prm_name: str,
        epsilon=1e-5,
    ):
        if self.output_dims_are_independent:
            return self._calc_jacobian_independent(f, f0, prm_name, epsilon)
        return self._calc_jacobian_full(f, f0, prm_name, epsilon)

    def _calc_jacobian_independent(
        self,
        f: Callable[[dict[str, fd.FlodymArray]], fd.FlodymArray],
        f0: fd.FlodymArray,
        prm_name: str,
        epsilon=1e-5,
    ):
        prm = self.prms[prm_name]
        original_prm = prm.copy()

        # dims in parameter but NOT in output — must loop over these
        reduced_dims = self.remove_fd_dims_if_present(self.prms_adj_dims[prm_name], f0.dims.letters)
        combined_dims = self.prms_adj_dims[prm_name].union_with(f0.dims)

        if not reduced_dims.letters:
            # No extra dims — single perturbation suffices
            prm[...] = prm * (1 + epsilon)
            f_perturbed = f(self.prms)
            prm[...] = original_prm
            J = (f_perturbed - f0) / epsilon
            return J

        J = fd.FlodymArray(dims=combined_dims)

        for slicer in self.iter_dim_slicers(reduced_dims):
            val = original_prm[slicer]

            prm[slicer] = val * (1 + epsilon)
            f_perturbed = f(self.prms)
            J[slicer] = (f_perturbed - f0) / epsilon

            prm[slicer] = val

        return J

    def _calc_jacobian_full(
        self,
        f: Callable[[dict[str, fd.FlodymArray]], fd.FlodymArray],
        f0: fd.FlodymArray,
        prm_name: str,
        epsilon=1e-5,
    ):
        """Assumption-free reference implementation: perturbs every parameter element
        individually, building the full output × parameter matrix. Used when
        `output_dims_are_independent` is False."""
        prm = self.prms[prm_name]
        original_prm = prm.copy()
        dims_to_adj = self.prms_adj_dims[prm_name]

        J = np.zeros((f0.size, dims_to_adj.total_size))

        for flat_idx, slicer in enumerate(self.iter_dim_slicers(dims_to_adj)):
            val = original_prm[slicer]

            # Perform perturbation (zero values are not corrected)
            prm[slicer] = val * (1 + epsilon)
            f_perturbed = f(self.prms)
            J[:, flat_idx] = self.flatten_fd_to_np(f_perturbed - f0) / epsilon

            # Restore original value
            prm[slicer] = val

        return J

    @staticmethod
    def iter_dim_slicers(dims: fd.DimensionSet):
        """
        Iterate over all element combinations of a DimensionSet, yielding dict slicers.

        Yields dicts like {'r': 'USA', 'u': 'Res'} for each element in the Cartesian product.
        Order matches numpy flatten (C-order): last dimension varies fastest.
        """
        items_per_dim = [d.items for d in dims]
        for dim_element in itertools.product(*items_per_dim):
            yield dict(zip(dims.letters, dim_element))

    def flatten_fd_to_np(self, arr: fd.FlodymArray) -> np.ndarray:
        """Flatten a FlodymArray into a 1D numpy array."""
        return arr.values.flatten()

    def flodym_jacobian_to_matrix(
        self,
        J: fd.FlodymArray,
        output_dims: fd.DimensionSet,
        param_dims: fd.DimensionSet,
    ) -> np.ndarray:
        """
        Convert a FlodymArray Jacobian into a 2D numpy sensitivity matrix.

        The Jacobian J has dimensions that are the union of output_dims and param_dims.
        Dimensions shared between output and parameter create block-diagonal structure:
        each element of the shared dimension only affects its corresponding output.

        Args:
            J: FlodymArray with dims = union(output_dims, param_dims)
            output_dims: Dimensions of the model output (e.g., region, stock_type)
            param_dims: Dimensions of the parameter being varied

        Returns:
            2D numpy array of shape (output_size, param_size)
        """
        output_size = output_dims.total_size
        param_size = param_dims.total_size
        S = np.zeros((output_size, param_size))

        # Identify shared vs unique dimensions
        shared_letters = set(output_dims.letters) & set(param_dims.letters)

        # Iterate over all output positions
        for out_idx, out_slicer in enumerate(self.iter_dim_slicers(output_dims)):
            # Iterate over all parameter positions
            for prm_idx, prm_slicer in enumerate(self.iter_dim_slicers(param_dims)):
                # Check if shared dimensions match
                # If they don't match, the sensitivity is zero (block-diagonal structure)
                shared_match = all(
                    out_slicer[letter] == prm_slicer[letter] for letter in shared_letters
                )

                if shared_match:
                    # Build the combined slicer for J
                    # J has all dimensions from both output and param
                    j_slicer = {**out_slicer, **prm_slicer}
                    S[out_idx, prm_idx] = J[j_slicer].values.item()

        return S

    def solve_lagrange_multipliers(
        self,
        sensitivities: dict[str, np.ndarray],
        residual_log: fd.FlodymArray,
    ) -> np.ndarray:
        """Solve A λ = r with A = Σ_p S_p diag(σ_p²) S_pᵀ (see class docstring)."""
        r = self.flatten_fd_to_np(residual_log)
        A = np.zeros((r.size, r.size))

        for prm_name, S in sensitivities.items():
            variances = self.get_variances(prm_name)
            A += (S * variances[np.newaxis, :]) @ S.T

        return np.linalg.solve(A, r)

    def calc_corrections(
        self,
        sensitivities: dict[str, np.ndarray],
        lmda: np.ndarray,
    ) -> dict[str, fd.FlodymArray]:
        """Correction factors exp(d_p)."""
        corrections = {}
        for prm_name, S in sensitivities.items():
            d = self.calc_log_correction(prm_name, S, lmda)
            corrections[prm_name] = d.apply(np.exp)
        return corrections

    def calc_log_correction(self, prm_name: str, S: np.ndarray, lmda: np.ndarray) -> fd.FlodymArray:
        """Log-correction d_p = -diag(σ_p²) S_pᵀ λ for a single parameter (see class docstring)."""
        d = -self.get_variances(prm_name) * (S.T @ lmda)
        return self.reshape_np_to_fd(d, self.prms_adj_dims[prm_name])

    def apply_corrections(self, corrections: dict[str, fd.FlodymArray]):
        """Apply correction factors to the output parameters (in their original dimensions)
        and re-normalize split parameters."""
        for prm_name, c in corrections.items():
            c_full = self.cast_correction_to_original_prm_dim(c)
            self.output_prms[prm_name][...] = self.output_prms[prm_name] * c_full
            self.normalize_output_parameter(prm_name)

    def get_variances(self, prm_name: str) -> np.ndarray:
        """Flattened variances σ_p² of the log-corrections, approximated by the squared
        relative standard deviations of the parameter."""
        return self.flatten_fd_to_np(self.rel_std(prm_name)) ** 2

    def _build_rel_stds(self) -> dict[str, float | fd.FlodymArray]:
        return {
            # BU parameters
            # TODO MI std could be calculated from source in mrmfa (maybe other parameters, too)
            "concrete_building_mi": fd.FlodymArray.from_dims_superset(
                dims_superset=self.dims,
                dim_letters=("r",),
                values=np.array(
                    [
                        0.2 if self.prms["industrialized_regions"][{"r": region}].values else 0.5
                        for region in self.dims["r"].items
                    ]
                ),
            ),
            "function_buildings_split": 0.2,
            "structure_buildings_split": 0.2,
            "floorspace": 0.4,
            "hibernating_stock_share": 0.5,
            # TD parameters
            "cement_losses": 0.2,
            "cement_production": 0.0,
            "cement_ratio": 0.1,
            "product_material_split": 0.4,
            "stock_type_split": 0.5,
            "lifetime_mean": 0.4,
            "lifetime_std": 0.0,
        }

    def rel_std(self, prm_name: str) -> fd.FlodymArray:
        """
        Get the relative standard deviation of a parameter.
        Returns a FlodymArray with the same dimensions as the parameter.
        """
        default_rel_std = 0.2

        out = self._rel_stds.get(prm_name)
        if out is None:
            logging.warning(
                "Relative standard deviation missing for %s; using default %f",
                prm_name,
                default_rel_std,
            )
            out = default_rel_std

        if isinstance(out, (float, int)):
            out = fd.FlodymArray.scalar(out)

        out = out.cast_to(self.prms_adj_dims[prm_name])
        return out

    def reshape_np_to_fd(
        self, flat_arr: np.ndarray, target_dims: fd.DimensionSet
    ) -> fd.FlodymArray:
        """Reshape a 1D numpy array back into a FlodymArray with the same shape as the template."""
        if flat_arr.size != target_dims.total_size:
            raise ValueError("Size of flat array does not match size of template.")
        reshaped_values = flat_arr.reshape(target_dims.shape)
        return fd.FlodymArray(dims=target_dims, values=reshaped_values)

    def cast_correction_to_original_prm_dim(
        self, correction_factor: fd.FlodymArray
    ) -> fd.FlodymArray:
        if REDUCED_STOCK_TYPE.letter not in correction_factor.dims.letters:
            return correction_factor

        # build new correction factor
        new_dims = correction_factor.dims.replace(REDUCED_STOCK_TYPE.letter, self.input_dims["s"])
        new_correction = fd.FlodymArray.full(dims=new_dims, fill_value=1.0)
        new_correction[{"s": REDUCED_STOCK_TYPE}] = correction_factor
        return new_correction

    def normalize_output_parameter(self, prm_name: str):
        """Renormalize a split parameter so it sums to 1 along its split dimension.

        Full splits (every dim item part of the reconciliation) are scaled proportionally.
        Partial splits (only `_reconciled_split_items` part of the reconciliation) keep their reconciled
        values and let the unused complement items absorb the residual `1 - sum(reconciled)`,
        preserving the complement's internal ratio (see `_apply_complement_normalization`).

        This is needed even when the model self-normalizes a split (via `get_shares_over`):
        the optimizer multiplies each share by a correction factor, and multiplying shares by
        different factors does not keep their sum at 1 (e.g. [0.7, 0.3] scaled by [1.1, 0.9]
        gives [0.77, 0.27], summing to 1.04). So the stored split must be renormalized.
        """
        if prm_name not in self._normalization_dims:
            return

        prm = self.output_prms[prm_name]
        letter = prm.dims[self._normalization_dims[prm_name][0]].letter

        if prm_name in self._reconciled_split_items:
            self._apply_complement_normalization(prm_name, prm, letter)
            return

        # full split: proportional normalization
        prm_sum = prm.sum_over(letter)
        # avoid division by zero: zero values can occur due to `REDUCED_STOCK_TYPE`
        prm_sum.values[prm_sum.values == 0] = 1
        prm[...] = prm / prm_sum

    def _apply_complement_normalization(self, prm_name: str, prm: fd.FlodymArray, letter: str):
        """Renormalize a partial split in place so it sums to 1 along its split dimension,
        without disturbing the reconciled correction.

        Only some items of a partial split feed the reconciliation (the "reconciled" items,
        e.g. concrete, or Res/Com); the others are the unused "complement" (e.g. mortar, or
        Civ/Ind). The reconciled items keep exactly the values the optimizer produced, and the
        complement is rescaled to take up whatever is left of the budget,
        `1 - sum(reconciled)`, keeping the complement's internal ratio fixed (so e.g.
        mortar = 1 - concrete, and Civ:Ind stays as in the input data).

        If the reconciled items already use up the whole budget (`sum(reconciled) >= 1`),
        there is no room for a positive complement; those regions fall back to plain
        proportional scaling of all items so none is driven to zero.
        """
        recon_items = self._reconciled_split_items[prm_name]

        # 0/1 indicator over the split dimension: which items are reconciled
        is_recon = fd.FlodymArray(
            dims=prm.dims.get_subset(letter),
            values=np.array([it in recon_items for it in prm.dims[letter].items], dtype=float),
        )

        # split the parameter into its reconciled part (complement positions zeroed) and its
        # complement part (reconciled positions zeroed)
        reconciled = prm * is_recon
        complement = prm - reconciled

        # normalize only the complement
        target = 1.0 - reconciled.sum_over(letter)
        coupled = reconciled + complement * (target / complement.sum_over(letter))

        # fall back to proportional scaling where the budget is already full
        overflow = target.apply(lambda x: (x <= 0.0).astype(float))  # 1 where sum(recon) >= 1
        if overflow.values.any():
            logging.warning(
                f"Reconciled shares of {prm_name} sum to >= 1 in some regions; "
                "falling back to proportional scaling there."
            )
        prm[...] = overflow * prm.get_shares_over(letter) + (1.0 - overflow) * coupled


class DependencyTracker(dict):
    """Dictionary that tracks accessed keys."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.accessed_keys = set()

    def __getitem__(self, key):
        # 1. Record that this key was used
        self.accessed_keys.add(key)

        # 2. Return the actual value so the math doesn't crash
        return super().__getitem__(key)


class AnalyzeParameterReconciliation:
    """Class to analyze parameter reconciliation results."""

    def __init__(
        self,
        pr: "CementParameterReconciliation",
        original_prms: dict[str, fd.Parameter],
        adjusted_prms: dict[str, fd.Parameter],
    ):
        self.pr = pr
        self.original_prms = deepcopy(original_prms)
        self.adjusted_prms = deepcopy(adjusted_prms)

        self.original_prms["floorspace"] = self.original_prms["floorspace"][
            {"t": pr._year_of_reconciliation}
        ]
        self.adjusted_prms["floorspace"] = self.adjusted_prms["floorspace"][
            {"t": pr._year_of_reconciliation}
        ]

    def calc_parameter_impact(
        self,
        f: Callable[[dict[str, fd.FlodymArray]], fd.FlodymArray],
        max_permutations: int = 100,
        random_seed: Optional[int] = None,
    ):
        """
        Calculate parameter impact using Shapley values.

        If the number of permutations (n!) exceeds max_permutations, Monte Carlo
        sampling is used instead of exhaustive enumeration.

        Args:
            f: Model function that takes parameters and returns a FlodymArray.
            max_permutations: Maximum number of permutations to evaluate. If n! exceeds
                this, random sampling is used. Default is 100 (covers up to n=4 exactly,
                 n=5 would be 120 permutations).
            random_seed: Optional seed for reproducibility when using Monte Carlo sampling.

        Returns:
            FlodymArray with Shapley values for each parameter.
        """
        # sort for a deterministic Parameter dimension order across runs
        relevant_prm_names = sorted(self.pr.get_relevant_parameters(f, self.original_prms))

        # for N parameters, there are N! permutations
        n = len(relevant_prm_names)
        total_permutations = math.factorial(n)

        # Decide whether to use full enumeration or Monte Carlo sampling
        use_monte_carlo = total_permutations > max_permutations
        num_samples = min(total_permutations, max_permutations)

        if use_monte_carlo:
            logging.info(
                f"Using Monte Carlo sampling for Shapley values: {num_samples} samples "
                f"out of {total_permutations} possible permutations (n={n} parameters)."
            )
            permutation_iterator = self.get_random_permutations(
                relevant_prm_names, num_samples, random_seed=random_seed
            )
        else:
            logging.info(
                f"Using full enumeration for Shapley values: {total_permutations} permutations (n={n} parameters)."
            )
            permutation_iterator = itertools.permutations(relevant_prm_names)

        # Initialize FlodymArray where total parameter contribution is stored
        f_dims = f(self.original_prms).dims
        param_dim = fd.Dimension(name="Parameter", letter="p", items=relevant_prm_names)
        dims = f_dims.prepend(param_dim)
        shapley_sums = fd.FlodymArray(dims=dims)

        for permutation in permutation_iterator:
            # Initialize the current parameters at original values
            p = {name: self.original_prms[name].copy() for name in relevant_prm_names}
            # Initialize the current state of f
            f0 = f(p)

            for prm_name in permutation:
                # Update ONE parameter to its 'adjusted' value
                p[prm_name] = self.adjusted_prms[prm_name]
                # Calculate new f value after change
                fnew = f(p)
                # Calculate marginal contribution
                marginal_contribution = fnew - f0
                # Add to the running total contribution of this parameter
                shapley_sums[prm_name] += marginal_contribution
                # Update f0 so the next parameter adds on top of this one
                f0 = fnew

        shapley_values = shapley_sums / num_samples

        if use_monte_carlo:
            # Calculate the total change caused by all parameters
            total_change = f(self.adjusted_prms) - f(self.original_prms)

            # Normalize Shapley values to ensure they sum to the total change
            shapley_sum = shapley_values.sum_over("p")
            normalization_factor = total_change / shapley_sum
            shapley_values *= normalization_factor
            if np.abs(normalization_factor.values).max() > 1.05:
                logging.warning(
                    "Large normalization factor applied to Shapley values: %s",
                    normalization_factor.values,
                )

        return shapley_values

    @staticmethod
    def get_random_permutations(elements, k, random_seed=None):
        """
        Returns k unique permutations, automatically selecting the best strategy
        based on the size of the input list. Respects the random seed if provided.
        """
        if random_seed is not None:
            random.seed(random_seed)

        n = len(elements)
        max_perms = math.factorial(n)

        if k > max_perms:
            raise ValueError(
                f"Limit exceeded: You requested {k} permutations, but only {max_perms} exist."
            )

        # STRATEGY 1: POOL METHOD
        # If the total number of possibilities is small (e.g., < 50,000),
        # it is faster to build them all and sample.
        # n=8 is 40,320 perms. n=9 is 362,880 perms.
        if max_perms < 5e4:
            all_perms = list(itertools.permutations(elements))
            return random.sample(all_perms, k)

        # STRATEGY 2: SET / REJECTION METHOD
        # For large lists, the universe of permutations is huge.
        # Probability of collision is low, so we just pick until we have k.
        unique_perms = set()
        while len(unique_perms) < k:
            unique_perms.add(tuple(random.sample(elements, n)))

        return [list(p) for p in unique_perms]
