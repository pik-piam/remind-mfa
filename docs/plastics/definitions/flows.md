| Dimensions    | Origin Process            | Destination Process       |
|:--------------|:--------------------------|:--------------------------|
| t, e, r       | System environment        | Feedstock(fossil)         |
| t, e, r       | System environment        | Feedstock(ccu)            |
| t, e, r       | Exports                   | System environment        |
| t, e, r       | System environment        | Imports                   |
| t, e, r       | System environment        | C4 input                  |
| t, e, r       | System environment        | Other Reactants           |
| t, e, r       | Losses                    | System environment        |
| t, e, r       | Atmosphere                | Feedstock(biomass)        |
| t, e, r       | Atmosphere                | Feedstock(daccu)          |
| t, e, r       | Feedstock(fossil)         | High Value Chemical input |
| t, e, r       | Feedstock(biomass)        | High Value Chemical input |
| t, e, r       | Feedstock(daccu)          | High Value Chemical input |
| t, e, r       | Feedstock(ccu)            | High Value Chemical input |
| t, e, r       | High Value Chemical input | Polymerization            |
| t, e, r       | C4 input                  | Polymerization            |
| t, e, r       | Other Reactants           | Polymerization            |
| t, e, r, m    | Polymerization            | Primary Market            |
| t, e, r       | Polymerization            | Losses                    |
| t, e, r, m    | Primary Market            | Fabrication               |
| t, e, r, m    | Primary Market            | Exports                   |
| t, e, r, m    | Imports                   | Primary Market            |
| t, e, r, m, g | Fabrication               | Good Market               |
| t, e, r, m, g | Good Market               | Use Phase                 |
| t, e, r, m, g | Good Market               | Exports                   |
| t, e, r, m, g | Imports                   | Good Market               |
| t, e, r, m, g | Use Phase                 | EoL                       |
| t, e, r, m    | EoL                       | Collected                 |
| t, e, r, m    | EoL                       | Uncollected               |
| t, e, r, m    | Collected                 | Mechanical Recycling      |
| t, e, r, m    | Collected                 | Chemical Recycling        |
| t, e, r, m    | Collected                 | Landfilled                |
| t, e, r, m    | Collected                 | Incineration              |
| t, e, r, m    | Uncollected               | Uncontrolled              |
| t, e, r, m    | Mechanical Recycling      | Primary Market            |
| t, e, r       | Chemical Recycling        | High Value Chemical input |
| t, e, r       | Chemical Recycling        | Emissions                 |
| t, e, r, m    | Mechanical Recycling      | Uncontrolled              |
| t, e, r, m    | Mechanical Recycling      | Incineration              |
| t, e, r       | Incineration              | Emissions                 |
| t, e, r       | Emissions                 | Captured                  |
| t, e, r       | Emissions                 | Atmosphere                |
| t, e, r       | Captured                  | Feedstock(ccu)            |
| t, e, r, m    | Waste Market              | Collected                 |
| t, e, r, m    | Collected                 | Waste Market              |
| t, e, r, m    | Waste Market              | Exports                   |
| t, e, r, m    | Imports                   | Waste Market              |