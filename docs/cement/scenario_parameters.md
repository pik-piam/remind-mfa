### Cement

- **`development_gdppc_low`**\
  *Type: plain*\
  GDP per capita (PPP) below which splits fully converge to their global means.
- **`development_gdppc_high`**\
  *Type: plain*\
  GDP per capita (PPP) above which regions keep their own splits.
- **`clinker_ratio`**\
  *Type: extrapolation (linear); Dimensions: r*\
  Clinker-to-cement mass ratio, per region.
- **`cement_ratio`**\
  *Type: extrapolation (linear); Dimensions: r, m*\
  Mass share of cement in newly produced construction materials, per region and material.
- **`lifetime_mean`**\
  *Type: extrapolation (linear); Dimensions: r*\
  Mean lifetime of cement stocks, per region.
- **`lifetime_std`**\
  *Type: extrapolation (linear); Dimensions: r*\
  Standard deviation of the lifetime of cement stocks, per region.
- **`reuse_share`**\
  *Type: extrapolation (linear); Dimensions: r, m*\
  Share of end-of-life construction materials that is reused, per region and material.

### Cement (bottom-up module)

- **`unoccupied_residential_stock_share`**\
  *Type: extrapolation (linear); Dimensions: r*\
  Share of residential stock that is not permanently occupied (vacant dwellings and second homes).
- **`residential_type_split`**\
  *Type: extrapolation (poly_mix); Dimensions: r, d*\
  Split of residential floor area into single-family and multi-family homes.
- **`structure_split`**\
  *Type: extrapolation (poly_mix); Dimensions: r, b, s*\
  Split of building end uses into structure types, per region.
- **`min_timber_share`**\
  *Type: array; Dimensions: r*\
  Minimum share of timber buildings the structure split converges to.
- **`concrete_building_mi`**\
  *Type: extrapolation (linear); Dimensions: r, b, s*\
  Material intensity of concrete (t/m2), per region, building end use and structure.
