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

class CementParameterReconciliation:
    """Parameter reconciliation of top-down and bottom-up models."""

    # TODO inherit from separate helper class?

    def __init__(
        self,
        ref_mfa: CommonMFASystem,
        uncoupled: bool = False,
    ):
        self.ref_mfa = ref_mfa
        self._year_of_reconciliation = ref_mfa.dims["h"].items[-1]

        self._reduced_stock_type = fd.Dimension(
            name="Reduced Stock Type", letter="u", items=["Res", "Com"]
        )
        # parameters will get one correction factor across all time steps.
        self._no_correction_dim_letters = ("t", "h")  # instead of df/dx, now calculating df/dd

        self.output_dims_are_independent = uncoupled
        # NB this does not mean that all parameter dimensions are independent, only that output dimensions, if existant in parameters

        # TODO set and skip over known sensitivity parameters
        # TODO check if I can use [...] more for flodym arrays to avoid dimension issues

        self.prepare_dims()
        self.prepare_prms()
        self.prepare_flws()
        self.prepare_stks()
        self.prepare_trds()

    def prepare_dims(self):
        dims = self.ref_mfa.dims
        self.input_dims = deepcopy(dims)
        self.dims = dims.replace("s", self._reduced_stock_type)

    def prepare_prms(self):
        prms = self.ref_mfa.parameters
        self.input_prms = deepcopy(prms)
        self.prms: dict[str, fd.Parameter] = {}
        self.prms_adj_dims: dict[str, fd.DimensionSet] = {}
        ref_prms = self.output_prms if hasattr(self, "output_prms") else prms
        for key, val in ref_prms.items():
            # reduce stock type dimension
            if "s" in val.dims.letters:
                val = val[{"s": self._reduced_stock_type}]
            # remove time dimension
            if key in ["floorspace"]:
                val = val[{"t": self._year_of_reconciliation}]
            self.prms[key] = val
            self.prms_adj_dims[key] = self.remove_fd_dims_if_present(
                val.dims, self._no_correction_dim_letters
            )

    def prepare_flws(self):
        flws = self.ref_mfa.flows
        self.input_flws = deepcopy(flws)
        self.flws: dict[str, fd.Flow] = {}
        for key, val in flws.items():
            val = deepcopy(val)
            if "s" in val.dims.letters:
                val = val[{"s": self._reduced_stock_type}]
            self.flws[key] = val

    def prepare_stks(self):
        stks = self.ref_mfa.stocks
        self.input_stks = deepcopy(stks)
        self.stks: dict[str, fd.Stock] = {}
        for key, val in stks.items():
            val = deepcopy(val)
            if "s" in val.dims.letters:
                val.inflow = val.inflow[{"s": self._reduced_stock_type}]
                val.outflow = val.outflow[{"s": self._reduced_stock_type}]
                val.stock = val.stock[{"s": self._reduced_stock_type}]
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
    ):
        """Iteratively correct parameters to reconcile top-down and bottom-up stocks.

        Each iteration linearises around the current working parameters, computes a
        least-squares log-correction, and applies it in-place.  Cumulative corrections
        are tracked so the final output is always expressed relative to the original
        input parameters.

        Args:
            max_iter: Maximum number of correction iterations.
            tol: Convergence tolerance.  Stop early when
                ``max(|log(td / bu)|) < tol``.  If *None*, always run
                ``max_iter`` iterations.
        """
        self.max_iter = max_iter
        self.output_prms = deepcopy(self.input_prms)
        self.total_correction_factors: dict[str, fd.FlodymArray] = {}

        for i in range(self.max_iter):
            self.td = self.calc_top_down_stock(self.prms).copy()
            self.bu = self.calc_bottom_up_stock(self.prms).copy()

            residual_log = self.td.apply(np.log) - self.bu.apply(np.log)
            mismatch = float(np.max(np.abs(residual_log.values)))

            percent_mismatch = float(
                np.max(np.abs(self.td.values - self.bu.values) / np.abs(self.bu.values)) * 100
            )
            logging.info(
                "Reconciliation iteration "
                f"{i + 1}/{self.max_iter}: "
                f"max |log(td/bu)| = {mismatch:.4f}, "
                f"max percent mismatch = {percent_mismatch:.2f}%"
            )

            if tol is not None and mismatch < tol:
                logging.info(
                    f"Converged after {i} iteration(s) "
                    f"(mismatch {mismatch:.4f} < tol {tol})."
                )
                break

            # Fresh sensitivity matrices each iteration (re-linearise around current prms)
            self.S_matrices = {}
            self.pre_compute_sensitivity(self.calc_top_down_stock, self.td)
            self.pre_compute_sensitivity(self.calc_bottom_up_stock, self.bu, denominator=True)

            self.pre_compute_lambda()
            self.calc_corrections()

            # update parameters and store total correction factors
            for prm_name, c in self.correction_factors.items():
                if prm_name in self.total_correction_factors:
                    self.total_correction_factors[prm_name] *= c
                else:
                    self.total_correction_factors[prm_name] = c
                c_full = self.cast_correction_to_original_prm_dim(c)
                self.output_prms[prm_name][...] = self.output_prms[prm_name] * c_full
                self.normalize_output_parameter(prm_name)
                # TODO improve FlodymArray to Parameter conversion
                self.output_prms[prm_name] = fd.Parameter(
                    name=self.output_prms[prm_name].name,
                    dims=self.output_prms[prm_name].dims,
                    values=self.output_prms[prm_name].values,
                )

            # set output prms as new curr prms
            self.prepare_prms()  # TODO this needs to become cleaner
            # TODO is this reset necessary?
            self.prepare_flws()
            self.prepare_stks()
            self.prepare_trds()  # not altered - therefore probably not necessary
            # resetting dims should not be necessary

        return self.output_prms

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

        # 2.2 Use only material (m) concrete [no mortar]
        concrete_mask = {"m": "concrete"}
        concrete_stock = product_stock[concrete_mask]

        return concrete_stock

    @staticmethod
    def calc_bottom_up_stock(prm: dict[str, fd.FlodymArray], stock_type_letter: str = "u"):
        """Bottom-up stock calculation for reconciliation."""

        # 1. Compute concrete stock through bottom-up calculation
        concrete_stk = (
            prm["floorspace"]
            * prm["function_buildings_split"]
            * prm["structure_buildings_split"]
            * prm["concrete_building_mi"]
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
        reduced_cement_stock = reduced_cement_stock.sum_over("b")

        # TODO move this to mrmfa as a parameter
        # Scale up Chinese building stock to account for hibernating stock
        # 17.4% unused buildings from https://www.nature.com/articles/s41558-025-02527-3?fromPaywallRec=false#Fig3
        reduced_cement_stock[{"r": "CHA"}] = reduced_cement_stock[{"r": "CHA"}] / (1.0 - 0.174)

        return reduced_cement_stock

    def pre_compute_sensitivity(
        self,
        f: Callable[[dict[str, fd.FlodymArray]], fd.FlodymArray],
        f0: fd.FlodymArray,
        denominator: bool = False,
    ):
        """
        Pre-compute sensitivity matrices for parameters used in the given model function.
        Pre-existing sensitivities are added to newly computed ones.
        """
        relevant_params = self.get_relevant_parameters(f, self.prms)

        # Initialize S_matrices dictionary if it doesn't exist
        if not hasattr(self, "S_matrices"):
            self.S_matrices = {}

        for prm_name in relevant_params:
            S_mat = self.calc_sensitivity(f, f0, prm_name, denominator=denominator)
            if prm_name in self.S_matrices:
                # TODO double check if that makes sense
                logging.info(
                    f"Sensitivity for parameter {prm_name} already exists; summing matrices."
                )
                self.S_matrices[prm_name] = self.S_matrices[prm_name] + S_mat
            else:
                self.S_matrices[prm_name] = S_mat

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
        denominator: bool = False,
    ):
        # TODO set jacobian to zero if std is zero.
        J = self.calc_jacobian(f, f0, prm_name)

        if self.output_dims_are_independent:
            # Convert FlodymArray Jacobian to numpy matrix and scale for logarithmic sensitivity
            S = self.flodym_jacobian_to_matrix(J / f0, f0.dims, self.prms_adj_dims[prm_name])
        else:
            f0_flat = self.flatten_fd_to_np(f0)[:, np.newaxis]
            S = J / f0_flat

        if denominator:
            return -S
        return S

    def calc_jacobian(
        self,
        f: Callable[[dict[str, fd.FlodymArray]], fd.FlodymArray],
        f0: fd.FlodymArray,
        prm_name: str,
        epsilon=1e-5,
    ):
        # TODO I could do everything with flodym by just introducing new parameter dimensions for output dimensions
        # matrix multiplication would then be (A*B).sum_over(dims), instead of A @ B
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

        if reduced_dims.total_size == 0:
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

    def pre_compute_lambda(self):
        """Solve Aλ = b for λ."""
        log_f = self.flatten_fd_to_np(
            self.td.apply(np.log) - self.bu.apply(np.log)
        )
        D = log_f.size
        A = np.zeros((D, D))
        Sd_sum = np.zeros(D)

        for prm_name, S in self.S_matrices.items():
            var_vec = self.get_sigma(prm_name)
            S_weighted = S * var_vec[np.newaxis, :]
            A += S_weighted @ S.T

            if self.total_correction_factors:
                d_accum = self.flatten_fd_to_np(
                    self.total_correction_factors[prm_name].apply(np.log)
                )
                Sd_sum += S @ d_accum

        b = log_f - Sd_sum
        self.lmda = np.linalg.solve(A, b)

    def get_sigma(self, prm_name: str) -> np.ndarray:
        rel_std = self.rel_std(prm_name)
        sigma = self.flatten_fd_to_np(rel_std) ** 2
        return sigma

    def rel_std(self, prm_name: str) -> fd.FlodymArray:
        """
        Get the relative standard deviation of a parameter.
        Returns a FlodymArray with the same dimensions as the parameter.
        """

        # TODO some parameters are manually created, they need rel_std of zero.

        default_rel_std = 0.2

        rel_std = {
            # BU parameters
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
            # TD parameters
            "cement_losses": 0.2,
            "cement_production": 0.0,
            "cement_ratio": 0.1,
            "product_material_split": 0.4,
            "stock_type_split": 0.5,
            "lifetime_mean": 0.4,
            "lifetime_std": 0.0,
        }

        out = rel_std.get(prm_name)
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

    def calc_corrections(self):
        self.correction_factors = {}
        # TODO self.S_matrices.keys() replace this with list of corrected parameters
        for prm_name in self.S_matrices.keys():
            log_correction = self.calc_log_correction(prm_name)
            self.correction_factors[prm_name] = log_correction.apply(np.exp)

    def calc_log_correction(self, prm_name: str) -> fd.FlodymArray:
        S = self.S_matrices[prm_name]
        grad = S.T @ self.lmda
        # TODO prepare sigma vector beforehand
        var_vec = self.get_sigma(prm_name)
        d = -var_vec * grad
        d = self.reshape_np_to_fd(d, self.prms_adj_dims[prm_name])
        if self.total_correction_factors:
            d -= self.total_correction_factors[prm_name].apply(np.log)
        return d

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
        # TODO this should be moved to material specific reconciliatoin
        if self._reduced_stock_type.letter not in correction_factor.dims.letters:
            return correction_factor

        # build new correction factor
        new_dims = correction_factor.dims.replace(
            self._reduced_stock_type.letter, self.input_dims["s"]
        )
        new_correction = fd.FlodymArray.full(dims=new_dims, fill_value=1.0)

        # fill calculated correction values where possible
        # TODO what about the other stock types that may have to be rescaled
        new_correction[{"s": self._reduced_stock_type}] = correction_factor
        return new_correction

    def normalize_output_parameter(self, prm_name: str):
        """
        Normalize share or split parameters to sum up to 1 along their relevant dimensions.
        """
        # TODO find better way to know which parameters need normalization and along which dimensions
        normalization_dims = {
            "structure_buildings_split": ("Structure",),
            "function_buildings_split": ("Function",),
            "product_material_split": ("Product Material",),
            "stock_type_split": ("Stock Type",),
        }
        if prm_name not in normalization_dims:
            return

        prm = self.output_prms[prm_name]
        prm_sum = prm.sum_over(normalization_dims[prm_name])
        # avoid division by zero: zero values can occur due to `self._reduced_stock_type`
        if "s" in prm_sum.dims.letters:
            prm_sum.values[prm_sum.values == 0] = 1
        prm[...] = prm / prm_sum

    def system_model(self, prms: dict[str, fd.FlodymArray]) -> fd.FlodymArray:
        """This can be used with original parameter dimensions."""
        for key, prm in prms.items():
            if "s" in prm.dims.letters:
                prms[key] = prm[{"s": self._reduced_stock_type}]
        td = self.calc_top_down_stock(prms)
        bu = self.calc_bottom_up_stock(prms)
        return td / bu


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

        # TODO I could also scale down to pr._reduced_stock_type here

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
                this, random sampling is used. Default is 1000 (covers up to n=6 exactly,
                n=7 would be 5040 permutations).
            random_seed: Optional seed for reproducibility when using Monte Carlo sampling.

        Returns:
            FlodymArray with Shapley values for each parameter.
        """
        relevant_prm_names = list(self.pr.get_relevant_parameters(f, self.original_prms))

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

        i = 0
        for permutation in permutation_iterator:
            i += 1
            if i >= num_samples:
                break
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
