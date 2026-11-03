"""Methods of the models that do not depend on a run: the blending functions."""

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

import blicket as bk
from blicks._helpers import VALUE

if TYPE_CHECKING:  # annotations only, so blicket list does not import remind-mfa
    from blicketconf import Run

bk.group("methods", title="Methods")

POSITION = "Blend position"


@bk.blick(
    title="Blending functions",
    unit="factor",
    plot=bk.plots.scatter(x=POSITION, y=VALUE, color="Type", along="Point"),
)
def blending_functions(run: "Run") -> pd.DataFrame:
    """Every blending function of the parameter extrapolation over the blend position, which runs
    from 0 at the start of the blend to 1 at its end; the functions are the same for every run,
    so this Blick changes only when the code does."""
    from remind_mfa.common.data_blending import BLEND_TYPES, blending_factor

    positions = np.linspace(-1, 2, 301)
    parts = [
        pd.DataFrame(
            {
                "Point": np.arange(len(positions)),
                "Type": blend_type,
                POSITION: positions,
                VALUE: blending_factor(positions, blend_type),
            }
        )
        for blend_type in BLEND_TYPES
    ]
    return pd.concat(parts, ignore_index=True)
