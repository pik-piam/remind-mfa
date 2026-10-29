# REMIND-MFA scenario data

Scenario results for prospective material demands and flows computed with [REMIND-MFA](https://github.com/pik-piam/remind-mfa).

## Which format?

The data is provided in the IAMC format, i.e. as CSV files (which can be loaded into Excel) with years as columns.
Regions are disaggregated, while all other dimensions are contained in the variable name (see below).
The model and scenario columns contain the same value in all rows.

## Which scenarios?

We share the SSP2 Current Policies scenario (NPi - National Policies implemented).

## Which regions?

The scope is global. Results are computed and shared in two regional aggregations:

  - the REMIND 12-region aggregation (the definition and three-letter codes are given in the file `mapping_remind12region.csv`), and
  - a country resolution (249 countries with ISO 3166 codes).

Note that these two datasets are from different model runs.
In particular, the stock extrapolation is different: The stock is regressed to historical regional data and subsequently adapted to each single region, so different aggregations will yield different results.

**CAVEAT** on the country-resolution dataset: Any MFA is only as good as its data. Especially for small regions, production and/or trade data are often unavailable or inaccurate, so they are reconstructed from more aggregated data sets. We advise to treat the country-resolution dataset with caution. We recommend to perform regional aggregation to regions fitting users' needs. As an alternative, users can also use the 12-region data set and disaggregate/re-aggregate it with their own method.
The data quality is also different across materials:
Trade data is available for most single countries for all materials.
Production data is available for 96 countries/regions for steel, 256 countries/regions for cement, but only 8 countries/regions for plastics, indicating potential inaccuracies especially for the plastics MFA. Regional aggregation is recommended to average out possible single-country errors.

The data is available in the region set it was computed with.
A global aggregation (region "World") is also available for all flows, stocks, and trades, but not for parameters, since these generally cannot simply be summed to obtain global values.

## Which years?

The temporal scope is 2025-2100 with annual resolution.
Historical years are not included, because the historical data partly builds on proprietary data, which we cannot share directly.

## Which variables?

We share all flows, stocks, trades, and parameters of the prospective MFA.
This means that the historical MFA and some auxiliary variables (e.g. from the stock extrapolation procedure) are not shared.
We provide a complete and an aggregated version of the dataset (files `data_<material>_<regions>_complete.csv` and `data_<material>_<regions>_aggregated.csv`), which are described below.

### Variable naming convention for the complete dataset:

The complete dataset contains the following variables:

```
<material>|flows|<flow name>
<material>|flows|<flow name>|<sub-dims>

<material>|stocks|<stock name>|stock
<material>|stocks|<stock name>|stock|<sub-dims>
<material>|stocks|<stock name>|inflow
<material>|stocks|<stock name>|inflow|<sub-dims>
<material>|stocks|<stock name>|outflow
<material>|stocks|<stock name>|outflow|<sub-dims>

<material>|trades|<trade name>|import
<material>|trades|<trade name>|import|<sub-dims>
<material>|trades|<trade name>|export
<material>|trades|<trade name>|export|<sub-dims>

<material>|parameters|<parameter name>
<material>|parameters|<parameter name>|<sub-dims>
```

Notes:

- Flows are named as `"<from_process> => <to_process>"`.
- `<sub-dims>` refers to the dimensions of a variable apart from region and time (such as end-use).
  If variables contain such additional dimensions, they are given once fully disaggregated and once aggregated along all dimensions except region and time.
- The list of all flows, stocks, trades, and parameters is given in the SI Section S2
- The list of all `<sub-dims>` combinations can be inferred from SI Section S2 through the dimension letters of each flow, stock, trade, or parameter, and the dimension items for each dimension in the dimension definition.
- Parameters are only given fully disaggregated, i.e. not aggregated along their sub-dims.

### Variables contained in the aggregated dataset:

The aggregated dataset contains the following variables:

```
<material>|flows|<flow name>
<material>|stocks|<stock name>|stock
<material>|stocks|<stock name>|inflow
<material>|stocks|<stock name>|outflow
<material>|trades|<trade name>|import
<material>|trades|<trade name>|export
```

Notes:

- Flows, stocks, and trades are given disaggregated only by region and time.
- Parameters are not given, as they mostly only have meaning when disaggregated.
- All these values are also contained in the complete dataset, but the aggregated version can be more practical, e.g. when searching for a variable name.

### Variables of special interest

- Total material consumption contained in end-use products can be found under
  ```
  <material>|stocks|use|inflow
  ```
  for all materials.

- Total material production can be found under different flows for different materials:
  - For plastics, it is the sum of the two flows
    ```
    plastics|flows|polymerization => primary_market
    +
    plastics|flows|aux_recyclate_market => primary_market
    ```
  - For steel, it is the flow
    ```
    steel|flows|forming => steel_market
    ```
  - For cement, it is the flow
    ```
    cement|flows|cement_production => cement_market
    ```
