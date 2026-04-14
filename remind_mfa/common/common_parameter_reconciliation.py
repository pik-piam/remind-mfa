import numpy as np
from typing import Callable, Tuple, Optional
import flodym as fd
import logging
import itertools
import math
import random

from remind_mfa.cement.cement_config import CementCfg
from remind_mfa.cement.cement_stock_models import CementStockModels

from copy import deepcopy
class ParameterReconciliation:
    """Parameter reconciliation of top-down and bottom-up models."""
    # TODO inherit from separate helper class?
    # TODO pydantic?

    def __init__(self, cfg: "CementCfg", prms: dict[str, fd.Parameter], dims: fd.DimensionSet, uncoupled: bool = False):

        self.cfg = cfg
        self._year_of_reconciliation = self.cfg.model_switches.parameter_reconciliation["year_of_reconciliation"]
        self._reduced_stock_type = fd.Dimension(name="Reduced Stock Type", letter="u", items=["Res", "Com"])
        # save computation time
        self._no_correction_dim_letters = ('t', 'h') # instead of df/dx, now calculating df/dd 

        self.output_dims_are_independent = uncoupled
        # NB this does not mean that all parameter dimensions are independent, only that output dimensions, if existant in parameters

        # TODO set and skip over known sensitivity parameters
        # TODO check if I can use [...] more for flodym arrays to avoid dimension issues

        self.prepare_dims(dims)
        self.prepare_prms(prms)

    def prepare_dims(self, dims: fd.DimensionSet):
        self.input_dims = deepcopy(dims)
        self.dims = dims.replace('s', self._reduced_stock_type)

    def prepare_prms(self, prms: dict[str, fd.Parameter]):
        self.input_prms = deepcopy(prms)
        self.prms: dict[str, fd.Parameter] = {}
        self.prms_adj_dims: dict[str, fd.DimensionSet] = {}
        for key, val in prms.items():
            # reduce stock type dimension
            if "s" in val.dims.letters:
                val = val[{"s": self._reduced_stock_type}]
            # remove time dimension
            if key in ["floorspace"]:
                val = val[{"t": self._year_of_reconciliation}]
            self.prms[key] = val
            self.prms_adj_dims[key] = self.remove_fd_dims_if_present(val.dims, self._no_correction_dim_letters)


    @staticmethod
    def remove_fd_dims_if_present(dims: fd.DimensionSet, letters_to_remove: Tuple) -> fd.DimensionSet:
        new_dims = dims
        for letter in letters_to_remove:
            if letter in new_dims.letters:
                new_dims = new_dims.drop(letter)
        return new_dims

    def correct_parameters(self):
        self.td = self.calc_top_down_stock(self.prms)
        self.bu = self.calc_bottom_up_stock(self.prms)

        # Assume (without loss of generality) target function of td/bu = 1s
        self.pre_compute_sensitivity(self.calc_top_down_stock, self.td)
        self.pre_compute_sensitivity(self.calc_bottom_up_stock, self.bu, denominator=True)

        self.pre_compute_lambda()
        self.calc_corrections()

        # TODO see if I really want to do the mulitplication here, or rather in parameter extrapolation?
        self.output_prms = deepcopy(self.input_prms)
        for prm_name, c in self.correction_factors.items():
            # TODO do I want to do the correction directy on self.prms, or rather return and or create self.corrected_prms?
            c = self.cast_correction_to_original_prm_dim(c)
            self.output_prms[prm_name][...] = self.input_prms[prm_name] * c
            self.normalize_parameter(prm_name)
            # transform from FlodymArray to Parameter
            self.output_prms[prm_name] = fd.Parameter(
                name=self.output_prms[prm_name].name,
                dims=self.output_prms[prm_name].dims,
                values=self.output_prms[prm_name].values,
            )
        return self.output_prms

    def calc_bottom_up_stock(self, prm: dict[str, fd.FlodymArray]):
        return CementStockModels.calc_stock_bottom_up_minimal(
            prm, 
            stock_type_dimletter=self._reduced_stock_type.letter
        )

    def calc_top_down_stock(self, prm: dict[str, fd.FlodymArray]):
        stk = CementStockModels.calc_stock_top_down_minimal(
            prm,
            lifetime_model=fd.LogNormalLifetime, # TODO take this from cfg
            time_letter="h",
        )

        # TODO see if there is a way to only calculate this year in the first place
        stk = stk[{"h": self._year_of_reconciliation}]
        return stk

    def pre_compute_sensitivity(self, f: Callable[[dict[str, fd.FlodymArray]], fd.FlodymArray], f0: fd.FlodymArray, denominator: bool = False):
        """
        Pre-compute sensitivity matrices for parameters used in the given model function.
        Pre-existing sensitivities are added to newly computed ones.
        """
        relevant_params = self.get_relevant_parameters(f, self.prms)

        # Initialize S_matrices dictionary if it doesn't exist
        if not hasattr(self, "S_matrices"):
            self.S_matrices = {}

        for prm_name in relevant_params:
            logging.info(f"Calculating sensitivity for parameter: {prm_name}")
            S_mat = self.calc_sensitivity(f, f0, prm_name, denominator=denominator)
            if prm_name in self.S_matrices:
                # TODO double check if that makes sense
                logging.info(f"Sensitivity for parameter {prm_name} already exists; summing matrices.")
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

    def calc_sensitivity(self, f: Callable[[dict[str, fd.FlodymArray]], fd.FlodymArray], f0: fd.FlodymArray, prm_name: str, denominator: bool = False):
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

    def calc_jacobian(self, f: Callable[[dict[str, fd.FlodymArray]], fd.FlodymArray], f0: fd.FlodymArray, prm_name: str, epsilon=1e-5):
        # TODO I could do everything with flodym by just introducing new parameter dimensions for output dimensions
        # matrix multiplication would then be (A*B).sum_over(dims), instead of A @ B
        if self.output_dims_are_independent:
            return self._calc_jacobian_independent(f, f0, prm_name)
        return self._calc_jacobian_full(f, f0, prm_name)

    def _calc_jacobian_independent(self, f: Callable[[dict[str, fd.FlodymArray]], fd.FlodymArray], f0: fd.FlodymArray, prm_name: str, epsilon=1e-5):
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

    def _calc_jacobian_full(self, f: Callable[[dict[str, fd.FlodymArray]], fd.FlodymArray], f0: fd.FlodymArray, prm_name: str, epsilon=1e-5):
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
                    out_slicer[letter] == prm_slicer[letter]
                    for letter in shared_letters
                )

                if shared_match:
                    # Build the combined slicer for J
                    # J has all dimensions from both output and param
                    j_slicer = {**out_slicer, **prm_slicer}
                    S[out_idx, prm_idx] = J[j_slicer].values.item()

        return S

    def pre_compute_lambda(self):
        """Solve Aλ = b for λ."""
        b = self.flatten_fd_to_np(self.td.apply(np.log) - self.bu.apply(np.log))
        D = b.size
        A = np.zeros((D, D))

        for prm_name, S in self.S_matrices.items():
            var_vec = self.get_sigma(prm_name)
            S_weighted = S * var_vec[np.newaxis, :]
            A += S_weighted @ S.T

        # solve for lambda
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
                dims_superset = self.dims,
                dim_letters = ('r',),
                values = np.array([0.2 if self.prms["industrialized_regions"][{"r": region}].values else 0.5 for region in self.dims["r"].items])
            ),
            "function_buildings_split": 0.2,
            "structure_buildings_split": 0.2,
            "floorspace": 1.,
            # TD parameters
            "cement_losses": 0.2,
            "cement_production": 0.01,
            "cement_trade": 0.0,
            "product_application_split": 0.4,
            "product_cement_content": 0.1,
            "product_density": 0.05,
            "product_material_application_transform": 0.0,
            "product_material_split": 0.4,
            "stock_type_split": 0.5,
            "use_lifetime_mean": 0.6,
            "use_lifetime_rel_std": 0.4,
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
        d = - var_vec * grad
        return self.reshape_np_to_fd(d, self.prms_adj_dims[prm_name])

    def reshape_np_to_fd(self, flat_arr: np.ndarray, target_dims: fd.DimensionSet) -> fd.FlodymArray:
        """Reshape a 1D numpy array back into a FlodymArray with the same shape as the template."""
        if flat_arr.size != target_dims.total_size:
            raise ValueError("Size of flat array does not match size of template.")
        reshaped_values = flat_arr.reshape(target_dims.shape)
        return fd.FlodymArray(dims=target_dims, values=reshaped_values)

    def cast_correction_to_original_prm_dim(self, correction_factor: fd.FlodymArray) -> fd.FlodymArray:
        if self._reduced_stock_type.letter not in correction_factor.dims.letters:
            return correction_factor

        # build new correction factor
        new_dims = correction_factor.dims.replace(self._reduced_stock_type.letter, self.input_dims["s"])
        new_correction = fd.FlodymArray.full(dims=new_dims, fill_value=1.0)

        # fill calculated correction values where possible
        new_correction[{"s": self._reduced_stock_type}] = correction_factor
        return new_correction


    def normalize_parameter(self, prm_name: str):
        """
        Normalize share or split parameters to sum up to 1 along their relevant dimensions.
        """
        # TODO find better way to know which parameters need normalization and along which dimensions
        normalization_dims = {
            "building_split": ("Structure", "Function",),
            "product_application_split": ("Product Application",),
            "product_material_split": ("Product Material",),
            "stock_type_split": ("Stock Type",),

        }
        if prm_name not in normalization_dims:
            return

        prm = self.output_prms[prm_name]
        if prm_name == "product_application_split":
            # TODO redefine parameter such that no such special treatment is necessary
            concrete_application_dim = fd.Dimension(name="Concrete Product Application", letter="y", items=['C15', 'C20', 'C30', 'C35'])
            mortar_application_dim = fd.Dimension(name="Mortar Product Application", letter="z", items=['finishing', 'masonry', 'maintenance'])
            concrete_prm = prm[{'a': concrete_application_dim}]
            mortar_prm = prm[{'a': mortar_application_dim}]
            sum_concrete = concrete_prm.sum_over('y')
            sum_mortar = mortar_prm.sum_over('z')
            prm[{'a': concrete_application_dim}] = concrete_prm / sum_concrete
            prm[{'a': mortar_application_dim}] = mortar_prm / sum_mortar
        else: 
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
            pr: "ParameterReconciliation",
            original_prms: dict[str, fd.Parameter],
            adjusted_prms: dict[str, fd.Parameter],
        ):
        self.pr = pr
        self.original_prms = deepcopy(original_prms)
        self.adjusted_prms = deepcopy(adjusted_prms)

        self.original_prms['floorspace'] = self.original_prms['floorspace'][{'t': pr._year_of_reconciliation}]
        self.adjusted_prms['floorspace'] = self.adjusted_prms['floorspace'][{'t': pr._year_of_reconciliation}]

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
            permutation_iterator = self.get_random_permutations(relevant_prm_names, num_samples, random_seed=random_seed)
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
            print(i)
            if i >= num_samples:
                break
            # Initialize the current parameters at original values
            p = {
                name: self.original_prms[name].copy() for name in relevant_prm_names
            }
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
            raise ValueError(f"Limit exceeded: You requested {k} permutations, but only {max_perms} exist.")

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