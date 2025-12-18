| Dimensions    | Name           | Process     | Stock Type            | Lifetime Model    |
|:--------------|:---------------|:------------|:----------------------|:------------------|
| t, r, s, m, a | in_use         | Use phase   | StockDrivenDSM        | LogNormalLifetime |
| t, r, m, a    | End of life    | End of life | InflowDrivenDSM       | FixedLifetime     |
| t, r, m       | atmosphere     | atmosphere  | SimpleFlowDrivenStock |                   |
| t, r, m, c    | carbonated_co2 | carbonation | InflowDrivenDSM       | FixedLifetime     |