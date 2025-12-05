| Dimensions    | Origin Process      | Destination Process   |
|:--------------|:--------------------|:----------------------|
| t, e, r, m    | sysenv              | virginfoss            |
| t, e, r, m    | sysenv              | virginbio             |
| t, e, r, m    | sysenv              | virgindaccu           |
| t, e, r, m    | sysenv              | virginccu             |
| t, e, r       | atmosphere          | virginbio             |
| t, e, r       | atmosphere          | virgindaccu           |
| t, e, r, m    | virginfoss          | virgin                |
| t, e, r, m    | virginbio           | virgin                |
| t, e, r, m    | virgindaccu         | virgin                |
| t, e, r, m    | virginccu           | virgin                |
| t, e, r, m    | virgin              | processing            |
| t, e, r, m    | virgin              | primary_market        |
| t, e, r, m    | primary_market      | processing            |
| t, e, r, m    | primary_market      | sysenv                |
| t, e, r, m    | sysenv              | primary_market        |
| t, e, r, m    | processing          | fabrication           |
| t, e, r, m    | processing          | intermediate_market   |
| t, e, r, m    | intermediate_market | fabrication           |
| t, e, r, m    | intermediate_market | sysenv                |
| t, e, r, m    | sysenv              | intermediate_market   |
| t, e, r, m, g | fabrication         | good_market           |
| t, e, r, m, g | good_market         | use                   |
| t, e, r, m, g | fabrication         | use                   |
| t, e, r, m    | good_market         | sysenv                |
| t, e, r, m    | sysenv              | good_market           |
| t, e, r, m, g | use                 | eol                   |
| t, e, r, m    | eol                 | collected             |
| t, e, r, m    | eol                 | mismanaged            |
| t, e, r, m    | collected           | reclmech              |
| t, e, r, m    | collected           | reclchem              |
| t, e, r, m    | collected           | landfill              |
| t, e, r, m    | collected           | incineration          |
| t, e, r, m    | mismanaged          | uncontrolled          |
| t, e, r, m    | reclmech            | processing            |
| t, e, r, m    | reclchem            | virgin                |
| t, e, r, m    | reclmech            | uncontrolled          |
| t, e, r, m    | reclmech            | incineration          |
| t, e, r       | incineration        | emission              |
| t, e, r       | emission            | captured              |
| t, e, r       | emission            | atmosphere            |
| t, e, r       | captured            | virginccu             |
| t, r          | sysenv              | good_market           |
| t, e, r, m    | waste_market        | collected             |
| t, e, r, m    | collected           | waste_market          |
| t, e, r, m    | waste_market        | sysenv                |
| t, e, r, m    | sysenv              | waste_market          |