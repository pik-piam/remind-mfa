import pandas as pd
import os
import re

# A citation list such as "[@Andrews2019], [@Kaufmann2024]" may be split on commas.
# Free-text sources may contain commas themselves and are kept as one opaque token.
CITATION_LIST_PATTERN = re.compile(r"\[@[^\]]+\](\s*,\s*\[@[^\]]+\])*")


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


def merge_parameters_sources():
    """Merge parameter files with source information and generate markdown documentation."""

    modules = ["steel", "plastics", "cement"]

    # Read sources file once
    sources_df = pd.read_csv("docs/mrmfa_sources.csv")

    for module in modules:
        # Define file paths
        params_file = f"docs/{module}/definitions/parameters.csv"
        output_file = f"docs/{module}/definitions/parameters.md"

        # Check if parameter file exists
        if not os.path.exists(params_file):
            print(f"Warning: {params_file} not found, skipping {module}")
            continue

        # Read the parameter file
        params_df = pd.read_csv(params_file)

        # Get module prefix
        prefix = module[:2]

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

        # Generate markdown
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(merged_df.to_markdown(index=False))
            f.write("\n")

        print(f"Generated {output_file}")


def on_pre_build(config):
    """Run before the build starts."""
    merge_parameters_sources()
    return config
