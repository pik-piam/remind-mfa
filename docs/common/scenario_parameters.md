### Common

- **`driver_scen`**\
  *Type: plain*\
  Name of the (SSP) scenario to use for all driver parameters with an `S` dimension
- **`saturation_level`**\
  *Type: plain*\
  Saturation level for material use per capita (unit depends on the material, e.g. t/capita)
- **`n_trend_years`**\
  *Type: array; Dimensions: r*\
  Number of most recent historical years used to determine the initial slope of the critically damped blend of in-use stock inflows
- **`flow_approaching_time`**\
  *Type: array; Dimensions: r*\
  Characteristic timescale in years of the critically damped blend of in-use stock inflows from historical trends to future values
- **`stock_factor`**\
  *Type: extrapolation (linear); Dimensions: r*\
  Scaling factor on the extrapolated in-use stock per capita, per region.
- **`trade_factor`**\
  *Type: extrapolation (poly_mix); Dimensions: r*\
  Scaling factor on future trade, per region.
- **`lifetime_factor_nature`**\
  *Type: extrapolation (poly_mix); Dimensions: r, u*\
  Lifetime extension factor of new age-cohorts (nature).
- **`lifetime_factor_nurture`**\
  *Type: extrapolation (poly_mix); Dimensions: r, u*\
  Lifetime extension factor of all age-cohorts by year (nurture).
