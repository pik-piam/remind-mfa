| Parameter                                        | Type               | Default                 | Description                                                              |
|:-------------------------------------------------|:-------------------|:------------------------|:-------------------------------------------------------------------------|
| model_class                                      | str                | PydanticUndefined       | Model class to use. Must be one of 'plastics', 'steel', or 'cement'.     |
| input_data_path                                  | str                | PydanticUndefined       | Path to the input data directory.                                        |
| customization                                    | ModelCustomization | PydanticUndefined       | Model customization parameters.                                          |
| customization.stock_extrapolation_class_name     | str                | PydanticUndefined       | Class name of the extrapolation subclass to use for stock extrapolation. |
| customization.lifetime_model_name                | str                | PydanticUndefined       | Class name of the lifetime model subclass to use for the in-use stock.   |
| customization.do_stock_extrapolation_by_category | bool               | False                   | Whether to perform stock extrapolation by good category.                 |
| customization.regress_over                       | str                | gdppc                   | Variable to use as a predictor for stock extrapolation.                  |
| customization.mode                               | Optional           |                         | Mode of the MFA model, e.g. 'stock_driven' or 'inflow_driven'.           |
| visualization                                    | VisualizationCfg   | PydanticUndefined       | Visualization configuration.                                             |
| visualization.do_visualize                       | bool               | True                    | Whether to create visualizations.                                        |
| visualization.use_stock                          | dict               | {'do_visualize': False} | Visualization configuration for use stock.                               |
| visualization.production                         | dict               | {'do_visualize': False} | Visualization configuration for production.                              |
| visualization.sankey                             | dict               | {'do_visualize': False} | Visualization configuration for sankey.                                  |
| visualization.extrapolation                      | dict               | {'do_visualize': False} | Visualization configuration for extrapolation.                           |
| visualization.do_show_figs                       | bool               | True                    | Whether to show figures.                                                 |
| visualization.do_save_figs                       | bool               | False                   | Whether to save figures.                                                 |
| visualization.plotting_engine                    | str                | plotly                  | Plotting engine to use for visualizations.                               |
| visualization.plotly_renderer                    | str                | browser                 | Plotly renderer to use for visualizations.                               |
| output_path                                      | str                | PydanticUndefined       | Path to the output directory.                                            |
| docs_path                                        | str                | PydanticUndefined       | Path to the documentation directory.                                     |
| do_export                                        | ExportCfg          | PydanticUndefined       | Export configuration.                                                    |
| do_export.csv                                    | bool               | True                    | Whether to export results as CSV files.                                  |
| do_export.pickle                                 | bool               | True                    | Whether to export results as pickle files.                               |
| do_export.assumptions                            | bool               | True                    | Whether to export assumptions as a txt file.                             |
| do_export.docs                                   | bool               | False                   | Whether to create documentation files.                                   |
| do_export.future_input                           | bool               | False                   | Whether to export results as future input data used in the model.        |
| do_export.iamc                                   | bool               | False                   | Whether to export results in IAMC format.                                |
