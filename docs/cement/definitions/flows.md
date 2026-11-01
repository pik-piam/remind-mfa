| Dimensions    | Origin Process         | Destination Process    |
|:--------------|:-----------------------|:-----------------------|
| t, r          | System Environment     | Clinker Production     |
| t, r          | Clinker Production     | Clinker Market         |
| t, r          | Clinker Production     | Losses                 |
| t, r          | Clinker Market         | exports                |
| t, r          | imports                | Clinker Market         |
| t, r          | Clinker Market         | Cement Production      |
| t, r          | System Environment     | Cement Production      |
| t, r          | Cement Production      | Cement Market          |
| t, r          | Cement Market          | exports                |
| t, r          | imports                | Cement Market          |
| t, r, u, m    | Cement Market          | Construction           |
| t, r, u, m    | System Environment     | Construction           |
| t, r, u, m, k | Construction           | Use Phase              |
| t, r          | Construction           | Losses                 |
| t, r, u, m, k | Use Phase              | Hibernating Stock      |
| t, r, u, m, k | Use Phase              | End-of-Life Management |
| t, r, u, m, k | End-of-Life Management | Reuse                  |
| t, r, u, m, k | Reuse                  | Use Phase              |
| t, r, u, m, k | End-of-Life Management | End-of-Life Waste      |
| t, r          | Losses                 | System Environment     |
| t, r          | exports                | System Environment     |
| t, r          | System Environment     | imports                |
