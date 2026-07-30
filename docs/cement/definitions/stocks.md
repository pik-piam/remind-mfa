| Dimensions    | Name           | Process     | Stock Type            | Lifetime Model    |
|:--------------|:---------------|:------------|:----------------------|:------------------|
| t, r, s, m, k | in_use         | Use phase   | StockDrivenDSM        | LogNormalLifetime |
| t, r, s, m, k | End of life    | End of life | InflowDrivenDSM       | FixedLifetime     |
| t, r          | Atmosphere     | Atmosphere  | SimpleFlowDrivenStock |                   |
| t, r, c       | carbonated_co2 | Carbonation | InflowDrivenDSM       | FixedLifetime     |
