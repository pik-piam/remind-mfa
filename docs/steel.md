# Steel MFA
## Methodology

### Stock extrapolation
In-use stocks are regressed separately in different product categories, which then add up to the total in-use stock. For each product category, we regress a common set of parameters for all regions. However, since historic data in single regions deviates from these curves, we apply region-dependent correction terms, which form a smooth transition from historic trends to the common regression.

## Processes
The following table lists the processes that are modelled in the steel MFA.

{% include-markdown "steel/definitions/processes.md" %}

## Dimensions
The following table presents the dimensions over which parameters and variables (stocks and flows incl. trades) are defined in the steel MFA.

{% include-markdown "steel/definitions/dimensions.md" %}

## Stocks
The following table presents the processes that are modelled as stocks in the steel MFA with their respective dimensions and the lifetime model that is employed.

{% include-markdown "steel/definitions/stocks.md" %}

## Flows
The following table presents all flows in the steel MFA with their respective dimensions and the processes that they connect.

{% include-markdown "steel/definitions/flows.md" %}

Flows that enter or leave markets are the exports and imports of the trades listed in the following table.

{% include-markdown "steel/definitions/trades.md" %}

## Parameters
The following table presents all exogenous parameters in the steel MFA with their respective dimensions.

{% include-markdown "steel/definitions/parameters.md" %}
