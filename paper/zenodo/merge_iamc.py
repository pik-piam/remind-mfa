"""Merge two Excel files by concatenating their rows.

Usage:
	python merge_output.py first.xlsx second.xlsx merged.xlsx

Optional:
	python merge_output.py first.xlsx second.xlsx merged.xlsx --sheet-name Data
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

REGIONS = {
    "h12": "remind12regions",
    "iso249": "countries",
}
DETAILS = {
	"agg": "aggregated",
	"complete": "complete",
}
MATERIALS = ["plastics", "steel", "cement"]

INPUT_BASE_DIR = Path(__file__).parents[2] / "data_out" / "paper"

OUTPUT_DIR = Path(__file__).parent

def get_df(material, regi_source, detail_source):
	dir = INPUT_BASE_DIR / f"paper_{material}_SSP2_{regi_source}"
	file = f"output_iamc_raw_{detail_source}.xlsx"
	return pd.read_excel(dir / file)

def main():
	for regi_source, regi_target in REGIONS.items():
		for detail_source, detail_target in DETAILS.items():
			dfs = [get_df(material, regi_source, detail_source) for material in MATERIALS]
			merged_df = pd.concat(dfs, ignore_index=True)
			merged_df.to_excel(
				OUTPUT_DIR / f"data_{regi_target}_{detail_target}.xlsx",
				index=False,
			)

if __name__ == "__main__":
	main()
