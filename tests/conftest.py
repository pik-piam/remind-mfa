from pathlib import Path

import pytest


@pytest.fixture
def scenarios_path(tmp_path: Path) -> Path:
    """Scenario folder with root `ROOT`, its children `B` and `A`, and grandchild `A_CHILD`.

    The children are listed out of alphabetical order to detect sorting, and the file uses the
    trailing-comma layout as well as comment and blank lines of `config/scenarios/inheritance.csv`.
    """
    (tmp_path / "inheritance.csv").write_text(
        "# Scenario inheritance\nscenario,parent,\n\nROOT,\nB,ROOT,\nA,ROOT,\nA_CHILD,A,\n",
        encoding="utf-8",
    )
    return tmp_path
