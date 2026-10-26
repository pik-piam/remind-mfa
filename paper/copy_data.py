"""Copy the IAMC output csv files of all materials into this folder and rename them.

Usage:
        python merge_iamc.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

REGIONS = {
    "h12": "remind12regions",
    "iso249": "countries",
}
DETAILS = {
    "agg": "aggregated",
    "complete": "complete",
}
MATERIALS = ["plastics", "steel", "cement"]

INPUT_BASE_DIR = Path(__file__).parents[1] / "data_out" / "paper"

OUTPUT_DIR = Path(__file__).parent / "zenodo"


def get_source_path(material, regi_source, detail_source):
    dir = INPUT_BASE_DIR / f"paper_{material}_SSP2_{regi_source}"
    file = f"output_iamc_raw_{detail_source}.csv"
    return dir / file


def main():
    for regi_source, regi_target in REGIONS.items():
        for detail_source, detail_target in DETAILS.items():
            for material in MATERIALS:
                shutil.copy2(
                    get_source_path(material, regi_source, detail_source),
                    OUTPUT_DIR / f"data_{material}_{regi_target}_{detail_target}.csv",
                )


if __name__ == "__main__":
    main()
