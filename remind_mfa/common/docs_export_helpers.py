"""Merge two BibTeX files into `docs/all_refs.bib`, keeping only unique entries.

This module deduplicates by BibTeX key. It first reads entries from
`mrmfa_sources.bib`, then `custom_refs.bib` (skipping duplicate keys).

"""

from typing import List, Tuple, Dict, Optional
import re


import pandas as pd


# A citation list such as "[@Andrews2019], [@Kaufmann2024]" may be split on commas.
# Free-text sources may contain commas themselves and are kept as one opaque token.
CITATION_LIST_PATTERN = re.compile(r"\[@[^\]]+\](\s*,\s*\[@[^\]]+\])*")



def merge_bib_files(src_paths: List[str], out_path: str) -> Tuple[int, int, int]:
    """Merge bib files from src_paths into out_path.

    Returns a tuple: (total_entries_read, duplicates_skipped, total_written)
    """
    seen_keys: Dict[str, str] = {}
    all_entries: List[str] = []
    total_read = 0
    duplicates = 0

    for path in src_paths:
        try:
            text = open(path, encoding="utf-8").read()
        except FileNotFoundError:
            # If a source file is missing, just continue (keeps behaviour simple)
            continue
        entries = _split_entries(text)
        for entry in entries:
            total_read += 1
            key = _extract_key(entry)

            # If key present and already seen, skip
            if key and key in seen_keys:
                duplicates += 1
                continue

            # Accept this entry
            all_entries.append(entry)
            if key:
                seen_keys[key] = entry

    # Write merged file with entries separated by a blank line
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(all_entries))

    written = len(all_entries)
    return total_read, duplicates, written


def merge_parameters_sources(sources_df: pd.DataFrame, params_df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Merge parameter files with source information and generate markdown documentation."""

    # Filter sources for this module (module-specific + common)
    module_sources = sources_df[sources_df["Filename"].str.startswith(f"{prefix}_")].copy()

    # Extract parameter name from filename (prefix_param.cs4r -> param)
    module_sources["Name"] = (
        module_sources["Filename"]
        .str.replace(f"{prefix}_", "", regex=True)
        .str.replace(".cs4r", "")
    )

    # Merge with parameters based on Name, rename Bibtex -> Sources
    merged_df = params_df.merge(
        module_sources[["Name", "Bibtex"]].rename(columns={"Bibtex": "Sources"}),
        on="Name",
        how="left",
    )

    # Replace NaN with empty string for cleaner display
    merged_df["Sources"] = merged_df["Sources"].fillna("")

    # Apply custom mapping: append CUSTOM_SOURCES to the sources from the csv file
    CUSTOM_SOURCES = {
        "carbon_content_materials": "Carbon contents of different polymers are calculated from their chemical structure. For broader categories (Other thermoplastics, other thermosets), rough assumptions and weighted averages were used.",
        "mechanical_recycling_yield": "[@Uekert23]",
        "chemical_recycling_yield": "[@Yadav23]",
        "reclmech_loss_uncontrolled_rate": "[@brown_potential_2023]",
        "lifetime_rel_std": "Expert guess",
        "waste_size_min": "[@Kaufmann2024]",
        "waste_size_max": "[@Kaufmann2024]",
        "cao_emission_factor": "Stoichiometry",
        "floorspace": "[@edgeb26]",
        "hibernating_stock_share": "[@Zhang26]",
    }
    if CUSTOM_SOURCES:
        mapped = merged_df["Name"].map(CUSTOM_SOURCES)
        # mask: a non-empty custom mapping exists
        has_custom = mapped.notna() & (mapped.astype(str).str.strip() != "")
        merged_df.loc[has_custom, "Sources"] = [
            _combine_sources(existing, custom)
            for existing, custom in zip(
                merged_df.loc[has_custom, "Sources"], mapped[has_custom]
            )
        ]

    return merged_df

def _split_entries(text: str) -> List[str]:
    """Split raw bibtex file content into individual entry strings.

    This finds occurrences of '@' starting an entry and slices between them.
    """
    # Find all start indices of entries (an '@' followed by word chars)
    starts = [m.start() for m in re.finditer(r"@\w+\s*\(", text)]
    # Also allow entries that use brace style: @article{key,
    starts += [m.start() for m in re.finditer(r"@\w+\s*\{", text)]
    starts = sorted(set(starts))
    if not starts:
        return []
    entries = []
    for i, s in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        entries.append(text[s:end].strip())
    return entries


def _extract_key(entry: str) -> Optional[str]:
    """Extract the BibTeX key from an entry, or None if not found."""
    m = re.match(r"@\w+\s*[\{\(]\s*([^,\s]+)", entry, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None

def _split_sources(value):
    """Split a source string into tokens, keeping free text intact."""
    value = str(value).strip()
    if not value:
        return []
    if not CITATION_LIST_PATTERN.fullmatch(value):
        return [value]
    return re.findall(r"\[@[^\]]+\]", value)


def _combine_sources(existing, custom):
    """Append custom source tokens to the existing ones, skipping duplicates."""
    tokens = _split_sources(existing)
    for token in _split_sources(custom):
        if token not in tokens:
            tokens.append(token)
    return ", ".join(tokens)


