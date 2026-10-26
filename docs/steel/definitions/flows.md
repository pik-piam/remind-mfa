| Dimensions   | Origin Process               | Destination Process          |
|:-------------|:-----------------------------|:-----------------------------|
| t, r         | extraction                   | steel_production_ore_based   |
| t, r         | steel_production_ore_based   | forming                      |
| t, r         | steel_production_ore_based   | losses                       |
| t, r         | scrap_pool                   | steel_production_scrap_based |
| t, r         | steel_production_scrap_based | forming                      |
| t, r         | steel_production_scrap_based | losses                       |
| t, r         | forming                      | steel_market                 |
| t, r         | forming                      | scrap_pool                   |
| t, r         | forming                      | losses                       |
| t, r         | manufacturing                | losses                       |
| t, r         | steel_market                 | manufacturing                |
| t, r         | steel_market                 | exports                      |
| t, r         | imports                      | steel_market                 |
| t, r, u      | manufacturing                | manufactured_products_market |
| t, r         | manufacturing                | scrap_pool                   |
| t, r, u      | manufactured_products_market | exports                      |
| t, r, u      | imports                      | manufactured_products_market |
| t, r, u      | manufactured_products_market | use                          |
| t, r, u      | use                          | hibernating                  |
| t, r, u      | use                          | eol_management               |
| t, r, u      | eol_management               | reuse                        |
| t, r, u      | reuse                        | use                          |
| t, r, u      | eol_management               | scrap_market                 |
| t, r, u      | eol_management               | eol_waste                    |
| t, r         | scrap_market                 | scrap_pool                   |
| t, r         | scrap_market                 | exports                      |
| t, r         | imports                      | scrap_market                 |
| t, r         | scrap_pool                   | excess_scrap                 |
| t, r         | exports                      | sysenv                       |
| t, r         | sysenv                       | imports                      |
| t, r         | losses                       | sysenv                       |
| t, r         | sysenv                       | extraction                   |
