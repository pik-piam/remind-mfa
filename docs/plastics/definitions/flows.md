| Dimensions    | Origin Process     | Destination Process   |
|:--------------|:-------------------|:----------------------|
| t, e, r, m    | System environment | Prim(fossil)          |
| t, e, r, m    | System environment | Prim(biomass)         |
| t, e, r, m    | System environment | Prim(daccu)           |
| t, e, r, m    | System environment | Prim(ccu)             |
| t, e, r       | Atmosphere         | Prim(biomass)         |
| t, e, r       | Atmosphere         | Prim(daccu)           |
| t, e, r, m    | Prim(fossil)       | Prim(total)           |
| t, e, r, m    | Prim(biomass)      | Prim(total)           |
| t, e, r, m    | Prim(daccu)        | Prim(total)           |
| t, e, r, m    | Prim(ccu)          | Prim(total)           |
| t, e, r, m    | Prim(total)        | Proc                  |
| t, e, r, m    | Prim(total)        | Prim Market           |
| t, e, r, m    | Prim Market        | Proc                  |
| t, e, r, m    | Prim Market        | System environment    |
| t, e, r, m    | System environment | Prim Market           |
| t, e, r, m    | Proc               | Fabri                 |
| t, e, r, m    | Proc               | Inter Market          |
| t, e, r, m    | Inter Market       | Fabri                 |
| t, e, r, m    | Inter Market       | System environment    |
| t, e, r, m    | System environment | Inter Market          |
| t, e, r, m, g | Fabri              | Good Market           |
| t, e, r, m, g | Good Market        | Use Phase             |
| t, e, r, m, g | Fabri              | Use Phase             |
| t, e, r, m    | Good Market        | System environment    |
| t, e, r, m    | System environment | Good Market           |
| t, e, r, m, g | Use Phase          | EoL                   |
| t, e, r, m    | EoL                | Collect               |
| t, e, r, m    | EoL                | Uncollected           |
| t, e, r, m    | Collect            | Mech recycling        |
| t, e, r, m    | Collect            | Chem recycling        |
| t, e, r, m    | Collect            | Landfill              |
| t, e, r, m    | Collect            | Incineration          |
| t, e, r, m    | Uncollected        | Uncontrolled          |
| t, e, r, m    | Mech recycling     | Proc                  |
| t, e, r, m    | Chem recycling     | Prim(total)           |
| t, e, r, m    | Mech recycling     | Uncontrolled          |
| t, e, r, m    | Mech recycling     | Incineration          |
| t, e, r       | Incineration       | Emissions             |
| t, e, r       | Emissions          | Captured              |
| t, e, r       | Emissions          | Atmosphere            |
| t, e, r       | Captured           | Prim(ccu)             |
| t, r          | System environment | Good Market           |
| t, e, r, m    | Waste Market       | Collect               |
| t, e, r, m    | Collect            | Waste Market          |
| t, e, r, m    | Waste Market       | System environment    |
| t, e, r, m    | System environment | Waste Market          |