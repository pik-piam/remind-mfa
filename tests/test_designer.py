"""Tests for the flodym designer entry point."""

from pathlib import Path

import flodym as fd
import numpy as np
import pytest

from remind_mfa.common.helpers import ModelNames
from remind_mfa.designer import REPO_ROOT, load


@pytest.mark.parametrize("model", list(ModelNames))
def test_systems_are_available_before_run(
    model: ModelNames, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    designer_model = load(model.value, configs=["default"], root=REPO_ROOT)

    systems = designer_model.systems

    assert set(systems) == {"historical", "future"}
    for system in systems.values():
        assert isinstance(system, fd.MFASystem)
        assert system.flows
        assert system.stocks


def test_cement_with_reconciliation_has_bottom_up_system(tmp_path: Path):
    reconciliation_config = tmp_path / "reconciliation.toml"
    reconciliation_config.write_text(
        "[cement.model_switches]\nparameter_reconciliation = true\n", encoding="utf-8"
    )
    designer_model = load("cement", configs=["default", reconciliation_config], root=REPO_ROOT)

    systems = designer_model.systems

    assert set(systems) == {"historical", "future", "bottom_up"}


def test_run_computes_systems_with_the_structure_shown_before():
    designer_model = load("steel", configs=["default"], root=REPO_ROOT)
    empty_systems = designer_model.systems

    computed_systems = designer_model.run()

    assert computed_systems.keys() == empty_systems.keys()
    for name, system in computed_systems.items():
        assert type(system) is type(empty_systems[name])
        assert system.flows.keys() == empty_systems[name].flows.keys()
        assert system.stocks.keys() == empty_systems[name].stocks.keys()
    assert designer_model.systems["future"] is computed_systems["future"]
    assert any(np.any(flow.values) for flow in computed_systems["future"].flows.values())


def test_rerun_reproduces_the_results():
    designer_model = load("steel", configs=["default"], root=REPO_ROOT)
    first_systems = designer_model.run()

    second_systems = designer_model.run()

    for name, flow in first_systems["future"].flows.items():
        np.testing.assert_allclose(second_systems["future"].flows[name].values, flow.values)
