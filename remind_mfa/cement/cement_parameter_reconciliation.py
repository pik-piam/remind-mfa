import numpy as np
from typing import Callable, Tuple, Optional
import flodym as fd
import logging
import itertools
import math
import random
from copy import deepcopy

from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.cement.cement_mfa_system_historical import InflowDrivenHistoricalCementMFASystem
from remind_mfa.cement.cement_mfa_system_future import StockDrivenCementMFASystem
from remind_mfa.cement.cement_mfa_system_bottom_up import (
    StockDrivenBottomUpCementMFASystem,
    aggregate_bu_to_common,
)


class CementParameterReconciliation:
    """Reconcile parameters of the top-down (td) and bottom-up (bu) cement stock models.

    Both models predict the in-use concrete stock in residential and commercial buildings
    in the last historical year, but they disagree. This class nudges the uncertain input
    parameters just enough to make them agree, moving each parameter as little as its
    uncertainty allows.

    How it works:
        Each parameter x_p is scaled by a factor exp(d_p), so d_p is its correction in log
        space. We look for the corrections that make the two models agree while staying as
        small as possible, letting more uncertain parameters move more:

            minimize    sum_p (d_p / sigma_p)^2    small, uncertainty-weighted corrections
            subject to  r(d) = log(td / bu) = 0    the two models agree

        where sigma_p is the relative uncertainty of parameter p. Parameters with zero
        uncertainty are fixed. The constraint is non-linear in d, so it is linearised around
        the current estimate d_hat and the linear problem is solved repeatedly, following
        the weighted least-squares data reconciliation of Cencic (2016), doi:
        10.1016/j.serj.2016.06.002, with measurements d = 0 (no correction a priori).
        Each iteration evaluates

            r   = log(td / bu)                 the mismatch at d_hat
            S_p = d r / d d_p                  how much parameter p shifts the mismatch
                                               (the "sensitivity", via finite differences),

        which turns the constraint into ``r + sum_p S_p (d_p - d_hat_p) = 0``. Its closed-form
        (KKT) solution (Cencic 2016, eq. 11) is the new total correction

            d_p = -sigma_p^2 * S_p^T lambda,
            (sum_p S_p sigma_p^2 S_p^T) lambda = r - sum_p S_p d_hat_p.

        The iteration stops when both the mismatch and the step d - d_hat vanish; d is then
        the constrained optimum. The corrected parameters are always computed from the input
        parameters as input * exp(d).

        In code: S_p = ``sensitivities[p]``, lambda = ``lmda``, r = ``residual_log``,
        d_p = ``log_corrections[p]``, sigma_p^2 = ``get_variances(p)``.

    Dimension handling:
        - The top-down side is computed for all end uses ``u`` and restricted to the common end
          use ``c`` (Residential/Commercial). The bottom-up side is computed at the bottom-up
          end-use resolution ``b`` (Residential Single-/Multi-Family, Commercial) and aggregated
          to ``c`` (Residential = Single-Family + Multi-Family). In ``c``, top-down and bottom-up
          information overlap.
        - Each parameter receives one correction factor per element of its dimensions
          except time (``t``/``h``): corrections are constant across all time steps.
        - Splits are corrected item by item, including items outside the reconciliation
          (Industrial/Civil Engineering, Mortar): they enter through the shares of the
          reconciled items.
        - The reconciled stock functions see all splits only as shares, so their norm does not
          matter during the reconciliation. The returned splits are re-normalized once to sum to
          1 (see `normalize_output_parameter`).
    """

    _normalization_dims: dict[str, tuple[str, ...]] = {
        "structure_split": ("Structure",),
        "residential_type_split": ("Residential Type",),
        "construction_material_split": ("Construction Material",),
        "end_use_split": ("End Use",),
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

        self.prepare_dims()

        # parameters will get one correction factor across all time steps.
        self._no_correction_dim_letters = ("t", "h")  # instead of df/dx, now calculating df/dd

        self.output_dims_are_independent = output_dims_are_independent

        self.input_prms = deepcopy(ref_mfa.parameters)
        self.prepare_prms(ref_mfa.parameters)
        self.prepare_flws()
        self.prepare_stks()
        self.prepare_trds()
        self._rel_stds = self._build_rel_stds()

    def prepare_dims(self):
        self.input_dims = deepcopy(self.ref_mfa.dims)
        self.common_end_use = self.input_dims["c"]

    def prepare_prms(self, source_prms: dict[str, fd.Parameter]):
        """Build the working parameters `prms` from `source_prms`, and the
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
        # remove time dimension
        if prm_name in ["floorspace"]:
            prm = prm[{"t": self._year_of_reconciliation}]
        return prm

    def prepare_flws(self):
        self.flws: dict[str, fd.Flow] = {}
        for key, val in self.ref_mfa.flows.items():
            self.flws[key] = deepcopy(val)  # protect ref_mfa flows from in-place modification

    def prepare_stks(self):
        self.stks: dict[str, fd.Stock] = {}
        for key, val in self.ref_mfa.stocks.items():
            self.stks[key] = deepcopy(val)

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
        max_iter: int = 50,
        tol_r: float = 1e-8,
        tol_step: float = 1e-8,
    ) -> dict[str, fd.Parameter]:
        """Iteratively correct parameters to reconcile top-down and bottom-up stocks.

        Each iteration linearises around the current working parameters, computes the
        constrained least-squares log-correction (see class docstring), and applies it to
        the input parameters.

        Args:
            max_iter: Maximum number of correction iterations.
            tol_r: Convergence tolerance of the mismatch ``max(|log(td / bu)|)``.
            tol_step: Convergence tolerance of the largest log-step ``max(|d - d_hat|)``.

        Returns:
            The corrected parameters in their original dimensions.
        """
        self.output_prms = deepcopy(self.input_prms)
        # total log-corrections d, flattened over prms_adj_dims
        log_corrections: dict[str, np.ndarray] = {}

        for i in range(max_iter):
            td = self.calc_top_down_stock(self.prms)
            bu = self.calc_bottom_up_stock(self.prms)
            residual_log = self.calc_residual_log(td, bu)
            mismatch = self.mismatch_logging(
                residual_log, td, bu, label=f"iteration {i + 1}/{max_iter}"
            )

            # fresh sensitivity matrices each iteration (re-linearise around current prms)
            sensitivities = self.compute_sensitivities(td, bu)
            lmda = self.solve_lagrange_multipliers(sensitivities, residual_log, log_corrections)
            new_log_corrections = {
                prm_name: self.calc_log_correction(prm_name, S, lmda)
                for prm_name, S in sensitivities.items()
            }
            max_step = max(
                float(np.max(np.abs(d - log_corrections.get(prm_name, 0.0))))
                for prm_name, d in new_log_corrections.items()
            )
            logging.info(
                f"Reconciliation iteration {i + 1}/{max_iter}: max |step| = {max_step:.2e}, "
                f"objective = {self.calc_objective(new_log_corrections):.6g}"
            )

            if mismatch < tol_r and max_step < tol_step:
                logging.info(f"Reconciliation converged after {i} iteration(s).")
                break

            log_corrections = new_log_corrections
            self.apply_corrections(log_corrections)
            # set output prms as new working prms
            self.prepare_prms(self.output_prms)
        else:
            # not converged: report the mismatch reached by the last applied corrections
            td = self.calc_top_down_stock(self.prms)
            bu = self.calc_bottom_up_stock(self.prms)
            self.mismatch_logging(self.calc_residual_log(td, bu), td, bu, label="final")
            logging.warning(f"Reconciliation did not converge in {max_iter} iterations.")

        for prm_name in self._normalization_dims:
            self.normalize_output_parameter(prm_name)
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
        # 1. Compute product stock (summed over construction materials) from historical MFA
        product_stock = InflowDrivenHistoricalCementMFASystem.compute_stock(
            prm, self.trds, self.flws, self.stks
        )

        # 2. Reduce dimensions to match bottom-up stock dimensions
        # 2.1 Use only reconciliation year
        product_stock = product_stock[{"h": self._year_of_reconciliation}]

        # 2.2 Use only the common end uses (Residential/Commercial)
        product_stock = product_stock[{"u": self.common_end_use}]

        # 2.3 Use only the reconciled material (concrete) [no mortar]
        concrete_stock = StockDrivenCementMFASystem.add_construction_material_split(
            product_stock, prm
        )[{"m": "Concrete"}]

        return concrete_stock

    def calc_bottom_up_stock(self, prm: dict[str, fd.FlodymArray]):
        """Bottom-up stock calculation for reconciliation."""
        # 1. Compute concrete stock bottom-up
        concrete_stk = StockDrivenBottomUpCementMFASystem.concrete_from_floorspace(
            prm["floorspace"], prm
        )

        # 2. Reduce dimensions to match top-down stock dimensions
        return aggregate_bu_to_common(concrete_stk.sum_over("s"), self.common_end_use)

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

        Yields dicts like {'r': 'USA', 'c': 'Residential'} for each element in the Cartesian
        product.
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
            output_dims: Dimensions of the model output (e.g., region, common end use)
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
        log_corrections: dict[str, np.ndarray],
    ) -> np.ndarray:
        """Solve A λ = r - Σ_p S_p d_hat_p with A = Σ_p S_p diag(σ_p²) S_pᵀ (see class
        docstring)."""
        r = self.flatten_fd_to_np(residual_log)
        A = np.zeros((r.size, r.size))

        for prm_name, S in sensitivities.items():
            variances = self.get_variances(prm_name)
            A += (S * variances[np.newaxis, :]) @ S.T
            if prm_name in log_corrections:
                r = r - S @ log_corrections[prm_name]

        if np.linalg.matrix_rank(A) < r.size:
            raise ValueError(
                "Reconciliation constraints are linearly dependent or not affected by any "
                "uncertain parameter; A = Σ_p S_p diag(σ_p²) S_pᵀ is singular."
            )
        return np.linalg.solve(A, r)

    def calc_log_correction(self, prm_name: str, S: np.ndarray, lmda: np.ndarray) -> np.ndarray:
        """Flattened total log-correction d_p = -diag(σ_p²) S_pᵀ λ for a single parameter
        (see class docstring)."""
        return -self.get_variances(prm_name) * (S.T @ lmda)

    def calc_objective(self, log_corrections: dict[str, np.ndarray]) -> float:
        """Objective Σ_p Σ (d_p / σ_p)² (fixed elements with σ_p = 0 have d_p = 0).
        Only used for logging."""
        objective = 0.0
        for prm_name, d in log_corrections.items():
            variances = self.get_variances(prm_name)
            uncertain = variances > 0
            objective += float(np.sum(d[uncertain] ** 2 / variances[uncertain]))
        return objective

    def apply_corrections(self, log_corrections: dict[str, np.ndarray]):
        """Set the output parameters (in their original dimensions) to the input parameters
        scaled by the correction factors exp(d_p)."""
        self.output_prms = deepcopy(self.input_prms)
        for prm_name, d in log_corrections.items():
            factor = self.reshape_np_to_fd(np.exp(d), self.prms_adj_dims[prm_name])
            self.output_prms[prm_name][...] = self.output_prms[prm_name] * factor

    def get_variances(self, prm_name: str) -> np.ndarray:
        """Flattened variances σ_p² of the log-corrections, approximated by the squared
        relative standard deviations of the parameter."""
        return self.flatten_fd_to_np(self.rel_std(prm_name)) ** 2

    def _build_rel_stds(self) -> dict[str, float | fd.FlodymArray]:
        return {
            # BU parameters
            # TODO MI std could be calculated from source in mrmfa (maybe other parameters, too)
            "concrete_building_mi": 0.2 + 0.3 * self.prms["development_weight"],
            "residential_type_split": 0.2,
            "structure_split": 0.2,
            "floorspace": 0.4,
            "unoccupied_residential_stock_share": 0.5,
            # TD parameters
            "cement_losses": 0.2,
            "cement_production": 0.0,
            "cement_ratio": 0.1,
            "construction_material_split": 0.4,
            "end_use_split": 0.5,
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

    def normalize_output_parameter(self, prm_name: str):
        """Renormalize a returned split parameter proportionally so it sums to 1 along its
        split dimension.

        The corrections multiply the items of a split by different factors, so the stored
        split no longer sums to 1. The reconciled stock functions only see shares and are
        blind to this, but the model after the reconciliation uses the raw values (mass
        balance of end-use and material split, mortar residential type split, concrete mass
        shares, derived global split means). Proportional scaling does not change the shares.
        """
        prm = self.output_prms[prm_name]
        letter = prm.dims[self._normalization_dims[prm_name][0]].letter
        prm_sum = prm.sum_over(letter)
        prm[...] = prm / prm_sum


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
