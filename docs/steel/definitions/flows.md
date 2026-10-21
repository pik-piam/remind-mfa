| Dimensions   | Origin Process              | Destination Process         |
|:-------------|:----------------------------|:----------------------------|
| t, r         | Ore Extraction              | Production from Ores        |
| t, r         | Production from Ores        | Forming                     |
| t, r         | Production from Ores        | Losses                      |
| t, r         | Scrap Pool                  | Production from Scrap       |
| t, r         | Production from Scrap       | Forming                     |
| t, r         | Production from Scrap       | Losses                      |
| t, r         | Forming                     | Steel Market                |
| t, r         | Forming                     | Scrap Pool                  |
| t, r         | Forming                     | Losses                      |
| t, r         | Manufacturing               | Losses                      |
| t, r         | Steel Market                | Manufacturing               |
| t, r         | Steel Market                | Exports                     |
| t, r         | Imports                     | Steel Market                |
| t, r, u      | Manufacturing               | Manufactured Product Market |
| t, r         | Manufacturing               | Scrap Pool                  |
| t, r, u      | Manufactured Product Market | Exports                     |
| t, r, u      | Imports                     | Manufactured Product Market |
| t, r, u      | Manufactured Product Market | Use Phase                   |
| t, r, u      | Use Phase                   | Hibernating stocks          |
| t, r, u      | Use Phase                   | End-of-Life Management      |
| t, r, u      | End-of-Life Management      | Reuse                       |
| t, r, u      | Reuse                       | Use Phase                   |
| t, r, u      | End-of-Life Management      | Old Scrap Market            |
| t, r, u      | End-of-Life Management      | End-of-Life Waste           |
| t, r         | Old Scrap Market            | Scrap Pool                  |
| t, r         | Old Scrap Market            | Exports                     |
| t, r         | Imports                     | Old Scrap Market            |
| t, r         | Scrap Pool                  | Excess Scrap                |
| t, r         | Exports                     | System environment          |
| t, r         | System environment          | Imports                     |
| t, r         | Losses                      | System environment          |
| t, r         | System environment          | Ore Extraction              |
