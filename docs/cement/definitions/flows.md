| Dimensions    | Origin Process      | Destination Process   |
|:--------------|:--------------------|:----------------------|
| t, r          | System environment  | Production: Clinker   |
| t, r          | Production: Clinker | Market: Clinker       |
| t, r          | Production: Clinker | System environment    |
| t, r          | Market: Clinker     | exports               |
| t, r          | imports             | Market: Clinker       |
| t, r          | Market: Clinker     | Production: Cement    |
| t, r          | System environment  | Production: Cement    |
| t, r          | Production: Cement  | Market: Cement        |
| t, r          | Market: Cement      | exports               |
| t, r          | imports             | Market: Cement        |
| t, r          | Market: Cement      | System environment    |
| t, r, s, m    | Market: Cement      | Production: Product   |
| t, r, s, m    | System environment  | Production: Product   |
| t, r, s, m, k | Production: Product | Use phase             |
| t, r, s, m, k | Use phase           | End of life           |
| t, r, s, m, k | End of life         | System environment    |
| t, r          | exports             | System environment    |
| t, r          | System environment  | imports               |
| t, r          | Production: Clinker | Atmosphere            |
| t, r, c       | Atmosphere          | Carbonation           |
