| Dimensions    | Origin Process         | Destination Process    |
|:--------------|:-----------------------|:-----------------------|
| t, r          | System environment     | Production: Clinker    |
| t, r          | Production: Clinker    | Market: Clinker        |
| t, r          | Production: Clinker    | Losses                 |
| t, r          | Market: Clinker        | exports                |
| t, r          | imports                | Market: Clinker        |
| t, r          | Market: Clinker        | Production: Cement     |
| t, r          | System environment     | Production: Cement     |
| t, r          | Production: Cement     | Market: Cement         |
| t, r          | Market: Cement         | exports                |
| t, r          | imports                | Market: Cement         |
| t, r          | Market: Cement         | Losses                 |
| t, r, u, m    | Market: Cement         | Construction           |
| t, r, u, m    | System environment     | Construction           |
| t, r, u, m, k | Construction           | Use phase              |
| t, r, u, m, k | Use phase              | Hibernating stock      |
| t, r, u, m, k | Use phase              | End-of-Life Management |
| t, r, u, m, k | End-of-Life Management | Reuse                  |
| t, r, u, m, k | Reuse                  | Use phase              |
| t, r, u, m, k | End-of-Life Management | End-of-Life Waste      |
| t, r          | Losses                 | System environment     |
| t, r          | exports                | System environment     |
| t, r          | System environment     | imports                |
