| Dimensions    | Origin Process     | Destination Process   |
|:--------------|:-------------------|:----------------------|
| t, r          | sysenv             | clinker_production    |
| t, r          | clinker_production | clinker_market        |
| t, r          | clinker_production | sysenv                |
| t, r          | clinker_market     | exports               |
| t, r          | imports            | clinker_market        |
| t, r          | clinker_market     | cement_production     |
| t, r          | sysenv             | cement_production     |
| t, r          | cement_production  | cement_market         |
| t, r          | cement_market      | exports               |
| t, r          | imports            | cement_market         |
| t, r          | cement_market      | sysenv                |
| t, r, u, m    | cement_market      | construction          |
| t, r, u, m    | sysenv             | construction          |
| t, r, u, m, k | construction       | use                   |
| t, r, u, m, k | use                | hibernating           |
| t, r, u, m, k | use                | eol_management        |
| t, r, u, m, k | eol_management     | reuse                 |
| t, r, u, m, k | reuse              | use                   |
| t, r, u, m, k | eol_management     | eol_waste             |
| t, r          | exports            | sysenv                |
| t, r          | sysenv             | imports               |
