"""Tests for the reconciliation algorithm of `CementParameterReconciliation` on a toy model."""

from copy import deepcopy

import flodym as fd
import numpy as np
import pytest

from remind_mfa.cement.cement_parameter_reconciliation import CementParameterReconciliation

REGION_DIM = fd.Dimension(name="Region", letter="r", items=["R1", "R2"])
SPLIT_DIM = fd.Dimension(name="Split", letter="s", items=["A", "B", "C"])


class ToyReconciliation(CementParameterReconciliation):
    """Reconciliation of the toy models td = a * share_A * fixed and bu = c (per region).

    With `linear=True`, the split is left out (td = a * fixed), so the problem is linear in
    log space.
    """

    _normalization_dims = {"split": ("Split",)}

    def __init__(
        self,
        prms: dict[str, fd.Parameter],
        rel_stds: dict[str, float | fd.FlodymArray],
        output_dims_are_independent: bool,
        linear: bool = False,
    ):
        self.linear = linear
        self.output_dims_are_independent = output_dims_are_independent
        self._no_correction_dim_letters = ("t", "h")
        self.input_prms = deepcopy(prms)
        self.prepare_prms(prms)
        self._rel_stds = rel_stds

    def calc_top_down_stock(self, prm: dict[str, fd.FlodymArray]) -> fd.FlodymArray:
        td = prm["a"] * prm["fixed"]
        if not self.linear:
            td = td * prm["split"].get_shares_over("s")[{"s": "A"}]
        return td

    def calc_bottom_up_stock(self, prm: dict[str, fd.FlodymArray]) -> fd.FlodymArray:
        return prm["c"] * 1.0


def make_prms(split_scale: float = 1.0) -> dict[str, fd.Parameter]:
    region_dims = fd.DimensionSet(dim_list=[REGION_DIM])
    split_dims = fd.DimensionSet(dim_list=[REGION_DIM, SPLIT_DIM])
    split_values = np.array([[0.5, 0.3, 0.2], [0.2, 0.5, 0.3]]) * split_scale
    return {
        "a": fd.Parameter(dims=region_dims, values=np.array([2.0, 3.0]), name="a"),
        "c": fd.Parameter(dims=region_dims, values=np.array([1.5, 0.4]), name="c"),
        "fixed": fd.Parameter(dims=region_dims, values=np.array([1.0, 1.2]), name="fixed"),
        "split": fd.Parameter(dims=split_dims, values=split_values, name="split"),
    }


REL_STD_A, REL_STD_C, REL_STD_SPLIT = 0.2, 0.1, 0.5
REL_STDS: dict[str, float | fd.FlodymArray] = {
    "a": REL_STD_A,
    "c": REL_STD_C,
    "fixed": 0.0,
    "split": REL_STD_SPLIT,
}
# log-space variances of lognormal parameters
VAR_A, VAR_C, VAR_SPLIT = (np.log1p(v**2) for v in (REL_STD_A, REL_STD_C, REL_STD_SPLIT))


def mismatch(rec: ToyReconciliation, prms: dict[str, fd.Parameter]) -> np.ndarray:
    return rec.calc_residual_log(
        rec.calc_top_down_stock(prms), rec.calc_bottom_up_stock(prms)
    ).values


@pytest.mark.parametrize("output_dims_are_independent", [True, False])
def test_linear_case_matches_closed_form(output_dims_are_independent: bool):
    """In log space, td = a * fixed, bu = c is linear: the optimum is known analytically."""
    prms = make_prms()
    rec = ToyReconciliation(prms, REL_STDS, output_dims_are_independent, linear=True)
    residual = mismatch(rec, prms)

    out = rec.correct_parameters()

    expected_d_a = -VAR_A * residual / (VAR_A + VAR_C)
    expected_d_c = VAR_C * residual / (VAR_A + VAR_C)
    np.testing.assert_allclose(np.log(out["a"].values / prms["a"].values), expected_d_a)
    np.testing.assert_allclose(np.log(out["c"].values / prms["c"].values), expected_d_c)
    np.testing.assert_allclose(out["fixed"].values, prms["fixed"].values)


@pytest.mark.parametrize("output_dims_are_independent", [True, False])
def test_nonlinear_case_reaches_constrained_optimum(output_dims_are_independent: bool):
    """The solution satisfies the constraint, keeps fixed parameters and normalized splits,
    and fulfills the optimality condition d_p = -σ_p² S_pᵀ λ per region, with S_a = 1,
    S_c = -1 and S_split = 1[k = A] - share_k evaluated at the solution. The split condition
    is checked via differences between items, as the normalization shifts d_split by a
    constant per region."""
    prms = make_prms()
    rec = ToyReconciliation(prms, REL_STDS, output_dims_are_independent)

    out = rec.correct_parameters()

    np.testing.assert_allclose(mismatch(rec, out), 0.0, atol=1e-10)
    np.testing.assert_allclose(out["fixed"].values, prms["fixed"].values)
    np.testing.assert_allclose(out["split"].sum_over("s").values, 1.0)
    d_a = np.log(out["a"].values / prms["a"].values)
    d_c = np.log(out["c"].values / prms["c"].values)
    lmda = -d_a / VAR_A
    np.testing.assert_allclose(d_c / VAR_C, lmda, rtol=1e-6)
    d_split = np.log(out["split"].values / prms["split"].values)
    sensitivity_split = np.eye(3)[0] - out["split"].values
    np.testing.assert_allclose(
        np.diff(d_split, axis=1) / VAR_SPLIT,
        -lmda[:, np.newaxis] * np.diff(sensitivity_split, axis=1),
        rtol=1e-5,
    )


def test_split_scaling_does_not_change_result():
    """The models only see shares, so scaling the input split must not change the result."""
    rec = ToyReconciliation(make_prms(), REL_STDS, output_dims_are_independent=True)
    rec_scaled = ToyReconciliation(make_prms(split_scale=3.0), REL_STDS, True)

    out = rec.correct_parameters()
    out_scaled = rec_scaled.correct_parameters()

    for prm_name in out:
        np.testing.assert_allclose(out_scaled[prm_name].values, out[prm_name].values, rtol=1e-6)


def test_no_uncertain_parameter_raises():
    rel_stds: dict[str, float | fd.FlodymArray] = {"a": 0.0, "c": 0.0, "fixed": 0.0, "split": 0.0}
    rec = ToyReconciliation(make_prms(), rel_stds, output_dims_are_independent=True)

    with pytest.raises(ValueError, match="singular"):
        rec.correct_parameters()
