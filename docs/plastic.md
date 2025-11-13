# Plastic MFA
## Methodology

### Stock extrapolation
For plastic stock extrapolation, the general method as described in the [Model overview](methodology.md) was slightly adjusted: Plastic stock per capita regressions over GDP per capita did not align well for different regions, as regions with lower GDP per capita currently have higher stocks per capita than more developed regions had at the same GDP per capita in the past. This was attributed to the fact that plastics is a rather novel material compared to steel and cement, and historic stocks of developed regions are therefore not representative for today's stocks in developing regions. To account for this effect, a weighted sum of logGDP per capita and time was used as a predictor in stock extrapolation according to the formula: 'log10(gdppc) * weight + time'. The weight (documented in the assumptions below) was determined from a regression of time vs. log10(gdppc) at constant stock per capita.

## Processes
The following table lists the processes that are modelled in the plastics MFA.

{!plastics/definitions/processes.md!}

## Dimensions
The following table presents the dimensions over which parameters and variables (stocks and flows incl. trades) are defined in the plastics MFA.

{!plastics/definitions/dimensions.md!}

## Stocks
The following table presents the processes that are modelled as stocks in the plastics MFA with their respective dimensions and the lifetime model that is employed. We use an auxiliary stock for the stock extrapolation with only the dimensions that are regressed separately (r, g) to save dimensions and computation time. The auxiliary stock is computed using a dynamic stock model. The results are then transferred to the higher-dimensional in-use-stock in the MFA system by multiplying stock, inflow and outflow with the parameters "material shares in goods" and "carbon content materials". This stock is modelled as a simple flow driven stock.

{!plastics/definitions/stocks.md!}

## Flows
The following table presents all flows in the plastics MFA with their respective dimensions and the processes that they connect.

{!plastics/definitions/flows.md!}

Flows that enter or leave markets are the exports and imports of the trades listed in the following table.

{!plastics/definitions/trades.md!}

## Parameters
The following table presents all exogenous parameters in the plastics MFA with their respective dimensions.

{!plastics/definitions/parameters.md!}

## Assumptions
{!plastics/assumptions.md!}
