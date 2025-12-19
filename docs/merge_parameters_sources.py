import pandas as pd
import os


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

        # Apply custom mapping: use CUSTOM_SOURCES for parameters with empty Sources
        CUSTOM_SOURCES = {
            "carbon_content_materials": "Data from stochiometric calculations and estimates based on expert judgement for broader categories",
            "mechanical_recycling_yield": "[@Uekert23]",
            "reclmech_loss_uncontrolled_rate": "[@brown_potential_2023]",
        }
        if CUSTOM_SOURCES:
            mapped = merged_df["Name"].map(CUSTOM_SOURCES)
            # mask: custom mapping exists AND current Sources is empty
            current_empty = merged_df["Sources"].astype(str).str.strip() == ""
            mapped_present = mapped.notna() & (mapped.astype(str).str.strip() != "")
            mask = current_empty & mapped_present
            merged_df.loc[mask, "Sources"] = mapped[mask]

        # Generate markdown
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(merged_df.to_markdown(index=False))
            f.write("\n")

        print(f"Generated {output_file}")


def on_pre_build(config):
    """Run before the build starts."""
    merge_parameters_sources()
    return config
