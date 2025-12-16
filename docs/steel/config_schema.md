| Parameter                                         | Type                   | Default   | Description                                                              |
|:--------------------------------------------------|:-----------------------|:----------|:-------------------------------------------------------------------------|
| model                                             | ModelNames             |           | Model to use. Must be one of 'plastics', 'steel', or 'cement'.           |
| input                                             | InputCfg               |           |                                                                          |
| input.madrat_output_path                          | str                    |           |                                                                          |
| input.force_extract_tgz                           | bool                   |           | Whether to force re-extraction of input data from tgz files.             |
| input.input_data_path                             | str                    |           | Path to the input data directory.                                        |
| input.scenarios_path                              | str                    |           | Path to the scenario definition directory.                               |
| input.input_data_version                          | str                    |           |                                                                          |
| model_switches                                    | ModelSwitches          |           | Model customization parameters.                                          |
| model_switches.scenario                           | str                    |           | Name of the scenario to use.                                             |
| model_switches.stock_extrapolation_class_name     | str                    |           | Class name of the extrapolation subclass to use for stock extrapolation. |
| model_switches.lifetime_model_name                | str                    |           | Class name of the lifetime model subclass to use for the in-use stock.   |
| model_switches.do_stock_extrapolation_by_category | bool                   | False     | Whether to perform stock extrapolation by good category.                 |
| model_switches.regress_over                       | RegressOverModes       |           | Variable to use as a predictor for stock extrapolation.                  |
| model_switches.parameter_extrapolation            | Optional               |           |                                                                          |
| visualization                                     | VisualizationCfg       |           | Visualization configuration.                                             |
| visualization.do_visualize                        | bool                   | True      | Whether to create visualizations for this entity                         |
| visualization.figures_path                        | str                    |           | Path to the figures directory.                                           |
| visualization.do_show_figs                        | bool                   | True      | Whether to show figures.                                                 |
| visualization.do_save_figs                        | bool                   | False     | Whether to save figures.                                                 |
| visualization.plotting_engine                     | str                    | plotly    | Plotting engine to use for visualizations.                               |
| visualization.plotly_renderer                     | str                    | browser   | Plotly renderer to use for visualizations.                               |
| visualization.use_stock                           | StockVisualizationCfg  |           | Visualization configuration for use stock.                               |
| visualization.use_stock.do_visualize              | bool                   | True      | Whether to create visualizations for this entity                         |
| visualization.use_stock.per_capita                | bool                   | False     | Whether to visualize stock per capita.                                   |
| visualization.use_stock.over_gdp                  | bool                   | False     | Whether to visualize stock over GDP. Alternative is over time            |
| visualization.use_stock.accumulate_gdp            | bool                   | False     |                                                                          |
| visualization.production                          | BaseVisualizationCfg   |           | Visualization configuration for production.                              |
| visualization.production.do_visualize             | bool                   | True      | Whether to create visualizations for this entity                         |
| visualization.sankey                              | SankeyVisualizationCfg |           | Visualization configuration for sankey.                                  |
| visualization.sankey.do_visualize                 | bool                   | True      | Whether to create visualizations for this entity                         |
| visualization.sankey.plotter_args                 | dict                   | {}        | dictionary of arguments to pass to the Sankey plotter                    |
| visualization.extrapolation                       | BaseVisualizationCfg   |           | Visualization configuration for extrapolation.                           |
| visualization.extrapolation.do_visualize          | bool                   | True      | Whether to create visualizations for this entity                         |
| export                                            | ExportCfg              |           | Export configuration.                                                    |
| export.do_export                                  | bool                   | True      | Whether to export this entity                                            |
| export.path                                       | str                    |           | Path to export folder                                                    |
| export.csv                                        | BaseExportCfg          |           | Whether to export results as CSV files.                                  |
| export.csv.do_export                              | bool                   | True      | Whether to export this entity                                            |
| export.csv.path                                   | str                    |           | Path to export folder                                                    |
| export.pickle                                     | BaseExportCfg          |           | Whether to export results as pickle files.                               |
| export.pickle.do_export                           | bool                   | True      | Whether to export this entity                                            |
| export.pickle.path                                | str                    |           | Path to export folder                                                    |
| export.assumptions                                | BaseExportCfg          |           | Whether to export assumptions as a txt file.                             |
| export.assumptions.do_export                      | bool                   | True      | Whether to export this entity                                            |
| export.assumptions.path                           | str                    |           | Path to export folder                                                    |
| export.docs                                       | BaseExportCfg          |           | Whether to create documentation files.                                   |
| export.docs.do_export                             | bool                   | True      | Whether to export this entity                                            |
| export.docs.path                                  | str                    |           | Path to export folder                                                    |
| export.iamc                                       | BaseExportCfg          |           | Whether to export results in IAMC format.                                |
| export.iamc.do_export                             | bool                   | True      | Whether to export this entity                                            |
| export.iamc.path                                  | str                    |           | Path to export folder                                                    |