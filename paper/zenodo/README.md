# What do we share?

Scenario results for prospective material demands and flows computed with REMIND-MFA

## Which format?

- IAMC format: Excel file with years as columns; regions disaggregated, other dimensions contained in variable name (see below)
- Model and scenario are always the same in this case

## Which scenarios?

- SSP2 Current Policies (NPi - National Policies implemented) scenario

## Which regions?

- Global scope, computed and shared in two regional aggregations:
  - REMIND 12-region aggregation (definition and three-letter codes see paper SM XXX)
  - Country-resolution (249 countries with ISO 3166 codes)

Note that these two datasets are from different model runs.
In particular, the stock extrapolation is different: The stock is regressed to historical regional data and subsequently adapted to each single regions, so different aggregations will yield different results.

CAVEAT on the country-resolution dataset: Any MFA is only as good as its data. Especially for small regions, production and/or trade data are often unavailable or inaccurate, so they are reconstructed from more aggregated data sets. We advise to treat the country-resolution dataset with caution, but users can perform their own regional aggregations on it.
The data quality is also different across materials:
Trade da is available for most single countries for all materials.
Production data is available for 96 countries/regions for steel, 256 countries/regions for cement, but only 8 countries/regions for plastics, indicating potential inaccuracies especially for the plastics MFA. Regional aggregations should be performed to average out possible single-country errors.

The data is available in the region set it was computed with.
A global aggregation (Region "World") is also available for all flows, stocks, and trades, but not parameters (since they can't generally be simply summed to get the global values)

## Which years?

- Temporal scope: 2025-2100 with annual resolution
  - Reason: Historical data partly builds on proprietary data, and we can't rule out directly sharing these data points.

## Which Variables?

- All flows, stocks, trades, and parameters of the prospective MFA
  - This means the historical MFA and some auxiliary variables (e.g. from the stock extrapolation procedure) are not shared.
- We provide a complete and an aggregated version:

### Variable naming convention for the complete dataset:

The complete dataset contains the following variables:

```
<material>|Flows|<flow name>
<material>|Flows|<flow name>|<sub-dims>

<material>|Stocks|<stock name>|Stock
<material>|Stocks|<stock name>|Stock|<sub-dims>
<material>|Stocks|<stock name>|Inflow
<material>|Stocks|<stock name>|Inflow|<sub-dims>
<material>|Stocks|<stock name>|Outflow
<material>|Stocks|<stock name>|Outflow|<sub-dims>

<material>|Trades|<trade name>|Imports
<material>|Trades|<trade name>|Imports|<sub-dims>
<material>|Trades|<trade name>|Exports
<material>|Trades|<trade name>|Exports|<sub-dims>

<material>|Paramaters|<parameter name>|<sub-dims>
```

Notes:
- Flows are named as "<from_process> => <to_process>"
- <sub-dims> refers to dimensions in the variables apart from region and time (such as end-use).
  If variables contain such additional dimensions, they're given once fully disaggregated, and once aggregated along all non-region-non-time dimensions.
- Paramaters are not aggregated

### Variables contained in the reduced dataset:

The reduced dataset contains the following variables.

```
<material>|Flows|<flow name>
<material>|Stocks|<stock name>|Stock
<material>|Stocks|<stock name>|Inflow
<material>|Stocks|<stock name>|Outflow
<material>|Trades|<trade name>|Imports
<material>|Trades|<trade name>|Exports
```

Notes:
- Flows, Stocks, and Trades are given, disaggregated only by region and time.
- All these values are also contained in the complete dataset - but a reduced version can be more practical, e.g. if searching for a variable name.

### Variables of special interest

- Total material consumption contained in end-use products can be found under <!-- TODO: stock name -->
  ```
  <material>|Stocks|use|Inflow
  ```
  for all materials.

- Total material production can be found under different flows for different materials:
  - plastics:
    ```
    plastics|flows|polymerization => primary_market
    +
    plastics|flows|aux_recyclate_trade => primary_market
    ```
  - steel:
    ```
    steel|flows|forming => ip_market
    ```
  - cement:
    ```
    cement|flows|prod_cement => market_cement
    ```
