import pandas as pd
import os

def merge_parameters_sources():
    """Merge parameter files with source information and generate markdown documentation."""
    
    modules = ['steel', 'plastics', 'cement']
    
    for module in modules:
        # Define file paths
        params_file = f'docs/{module}/definitions/parameters.csv'
        sources_file = 'docs/mrmfa_sources.csv'
        output_file = f'docs/{module}/definitions/parameters.md'
        
        # Check if parameter file exists
        if not os.path.exists(params_file):
            print(f"Warning: {params_file} not found, skipping {module}")
            continue
        
        # Read the files
        params_df = pd.read_csv(params_file)
        sources_df = pd.read_csv(sources_file)
        
        # Create mapping from parameter name to cs4r filename
        # For plastic: collection_rate -> pl_collection_rate.cs4r
        # For steel: fabrication_yield -> st_fabrication_yield.cs4r
        # For cement: cement_production -> ce_cement_production.cs4r
        
        prefix = {'steel': 'st', 'plastics': 'pl', 'cement': 'ce'}[module]
        
        # Add cs4r filename column to params
        params_df['cs4r_file'] = params_df['Name'].apply(
            lambda x: f"{prefix}_{x}.cs4r"
        )
        
        # Merge with sources
        merged_df = params_df.merge(
            sources_df[['Filename', 'Source', 'Bibtex']], 
            left_on='cs4r_file', 
            right_on='Filename', 
            how='left'
        )
        
        # Drop unnecessary columns
        merged_df = merged_df.drop(columns=['cs4r_file', 'Filename'])

        # Replace NaN with empty string for cleaner display
        merged_df['Source'] = merged_df['Source'].fillna('')
        merged_df['Bibtex'] = merged_df['Bibtex'].fillna('')
        
        # Generate markdown
        with open(output_file, 'w', encoding='utf-8') as f:
            # Convert to markdown table
            f.write(merged_df.to_markdown(index=False))
            f.write("\n")
        
        print(f"Generated {output_file}")

def on_pre_build(config):
    """Run before the build starts."""
    merge_parameters_sources()
    return config