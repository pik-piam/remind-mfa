| Dimensions    | Origin Process               | Destination Process          |
|:--------------|:-----------------------------|:-----------------------------|
| t, e, r       | sysenv                       | feedfoss                     |
| t, e, r       | sysenv                       | feedccu                      |
| t, e, r       | exports                      | sysenv                       |
| t, e, r       | sysenv                       | imports                      |
| t, e, r       | sysenv                       | c4_production                |
| t, e, r       | sysenv                       | other_reactants              |
| t, e, r       | losses                       | sysenv                       |
| t, e, r       | atmosphere                   | feedbio                      |
| t, e, r       | atmosphere                   | feeddaccu                    |
| t, e, r       | feedfoss                     | hvc_production               |
| t, e, r       | feedbio                      | hvc_production               |
| t, e, r       | feeddaccu                    | hvc_production               |
| t, e, r       | feedccu                      | hvc_production               |
| t, e, r       | hvc_production               | polymerization               |
| t, e, r       | c4_production                | polymerization               |
| t, e, r       | other_reactants              | polymerization               |
| t, e, r, p    | polymerization               | primary_market               |
| t, e, r       | polymerization               | losses                       |
| t, e, r, p    | primary_market               | manufacturing                |
| t, e, r, p    | primary_market               | exports                      |
| t, e, r, p    | imports                      | primary_market               |
| t, e, r, p, u | manufacturing                | manufactured_products_market |
| t, e, r, p, u | manufactured_products_market | use                          |
| t, e, r, p, u | manufactured_products_market | exports                      |
| t, e, r, p, u | imports                      | manufactured_products_market |
| t, e, r, p, u | use                          | eol_management               |
| t, e, r, p, u | eol_management               | reuse                        |
| t, e, r, p, u | reuse                        | use                          |
| t, e, r, p    | eol_management               | sorting                      |
| t, e, r, p    | eol_management               | mismanaged                   |
| t, e, r, p    | sorting                      | reclmech                     |
| t, e, r, p    | sorting                      | reclchem                     |
| t, e, r, p    | sorting                      | landfill                     |
| t, e, r, p    | sorting                      | incineration                 |
| t, e, r, p    | mismanaged                   | uncontrolled                 |
| t, e, r, p    | reclmech                     | aux_recyclate_market         |
| t, e, r, p    | aux_recyclate_market         | primary_market               |
| t, e, r       | reclchem                     | aux_recl_feedstock_market    |
| t, e, r       | aux_recl_feedstock_market    | hvc_production               |
| t, e, r       | reclchem                     | emission                     |
| t, e, r, p    | reclmech                     | uncontrolled                 |
| t, e, r, p    | reclmech                     | incineration                 |
| t, e, r       | incineration                 | emission                     |
| t, e, r       | emission                     | captured                     |
| t, e, r       | emission                     | atmosphere                   |
| t, e, r       | captured                     | feedccu                      |
| t, e, r, p    | waste_market                 | sorting                      |
| t, e, r, p    | sorting                      | waste_market                 |
| t, e, r, p    | waste_market                 | exports                      |
| t, e, r, p    | imports                      | waste_market                 |
| t, e, r, p    | aux_recyclate_market         | exports                      |
| t, e, r, p    | imports                      | aux_recyclate_market         |
| t, e, r       | aux_recl_feedstock_market    | exports                      |
| t, e, r       | imports                      | aux_recl_feedstock_market    |
