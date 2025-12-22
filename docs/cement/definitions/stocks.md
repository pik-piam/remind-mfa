| Dimensions    | Name           | Process     | Stock Type            | Lifetime Model    |
|:--------------|:---------------|:------------|:----------------------|:------------------|
| t, r, s, m, a | in_use         | Use phase   | StockDrivenDSM        | LogNormalLifetime |
| t, r, m, a, s | End of life    | End of life | InflowDrivenDSM       | FixedLifetime     |
| t, r, m, s    | Atmosphere     | Atmosphere  | SimpleFlowDrivenStock |                   |
| t, r, m, c, s | carbonated_co2 | Carbonation | InflowDrivenDSM       | FixedLifetime     |
