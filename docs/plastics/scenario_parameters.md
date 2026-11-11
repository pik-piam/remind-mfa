### Plastics

- **`waste_imports`**\
  *Type: extrapolation (linear); Dimensions: r*\
  Plastic waste imports, per region.
- **`waste_exports`**\
  *Type: extrapolation (linear); Dimensions: r*\
  Plastic waste exports, per region.
- **`collection_rate`**\
  *Type: extrapolation (converge_quadratic); Dimensions: r*\
  Share of non-reused end-of-life plastics that is collected for sorting.
- **`landfill_rate`**\
  *Type: extrapolation (converge_quadratic); Dimensions: r*\
  Share of collected waste that is landfilled.
- **`mechanical_recycling_rate`**\
  *Type: extrapolation (converge_quadratic); Dimensions: r*\
  Share of collected waste that is mechanically recycled.
- **`chemical_recycling_rate`**\
  *Type: extrapolation (hermite); Dimensions: r*\
  Share of collected waste that is chemically recycled.
- **`bio_production_rate`**\
  *Type: extrapolation (hermite); Dimensions: r*\
  Share of primary HVC production from bio-based feedstock.
- **`daccu_production_rate`**\
  *Type: extrapolation (hermite); Dimensions: r*\
  Share of primary HVC production from DACCU feedstock.
- **`emission_capture_rate`**\
  *Type: extrapolation (linear); Dimensions: r*\
  Share of carbon emissions from incineration and chemical recycling that is captured.
- **`polymer_shares_use_inflow`**\
  *Type: extrapolation (linear)*\
  Polymer shares of the in-use stock inflow; held at the last historical value.
- **`reuse_share`**\
  *Type: extrapolation (linear); Dimensions: r, u*\
  Share of end-of-life products that is reused, per region and good.
