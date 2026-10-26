from functools import cached_property
from pathlib import Path
from typing import Optional

import pandas as pd

# Region sets from finest to coarsest: each set is an aggregation of the previous ones.
REGION_SETS = ("iso249", "eu21", "h12")

# piamMappings files mapping iso249 countries to the regions of the other sets.
MAPPING_FILES = {
    "eu21": "regionmapping_21_EU11.csv",
    "h12": "regionmappingH12.csv",
}


class RegionAggregations:
    """Resolves regions of coarser region sets to the regions of the current set.

    The mapping files are only read once a region has to be resolved, and the mapping
    between two region sets is only built when it is needed.
    """

    def __init__(self, mappings_path: str | Path, regions: list[str]):
        self.mappings_path = Path(mappings_path)
        self.regions = list(regions)
        self._mappings: dict[str, pd.Series] = {}

    def members(self, region: str) -> Optional[list[str]]:
        """Regions of the current set that the aggregate region consists of.

        Returns None if the region is not part of any aggregation of the current set.
        """
        if self.current_set is None:
            return None
        for aggregate_set in REGION_SETS[REGION_SETS.index(self.current_set) + 1 :]:
            mapping = self._mapping(aggregate_set)
            members = [r for r in self.regions if mapping.get(r) == region]
            if members:
                return members
        return None

    @cached_property
    def iso_mappings(self) -> pd.DataFrame:
        """Region of each region set, indexed by iso249 country code."""
        mappings = {}
        for region_set, filename in MAPPING_FILES.items():
            path = self.mappings_path / filename
            if not path.exists():
                raise FileNotFoundError(
                    f"Region mapping file {path} not found. Initialize the piam_mappings "
                    "submodule with `git submodule update --init data_in/piam_mappings`."
                )
            df = pd.read_csv(path, sep=";")
            mappings[region_set] = df.set_index("CountryCode")["RegionCode"]
        df = pd.DataFrame(mappings)
        df["iso249"] = df.index
        return df

    @cached_property
    def current_set(self) -> Optional[str]:
        """The region set the current regions belong to, or None if none matches."""
        for region_set in REGION_SETS:
            if set(self.regions) <= set(self.iso_mappings[region_set]):
                return region_set
        return None

    def _mapping(self, aggregate_set: str) -> pd.Series:
        """Aggregate region of each region of the current set."""
        if aggregate_set not in self._mappings:
            pairs = self.iso_mappings[[self.current_set, aggregate_set]].drop_duplicates()
            if not pairs[self.current_set].is_unique:
                raise ValueError(
                    f"Region set '{self.current_set}' does not aggregate uniquely "
                    f"to '{aggregate_set}'."
                )
            self._mappings[aggregate_set] = pairs.set_index(self.current_set)[aggregate_set]
        return self._mappings[aggregate_set]
