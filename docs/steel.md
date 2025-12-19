# Steel MFA
## Methodology

### Stock extrapolation
In-use stocks are regressed separately in different product categories, which then add up to the total in-use stock. For each product category, we regress a common set of parameters for all regions. However, since historic data in single regions deviates from these curves, we apply region-dependent correction terms, which form a smooth transition from historic trends to the common regression.
In the regression, we apply region-specific saturation levels based on expert judgement.
In some regions, we also vary the speed of convergence towards this saturation level based on expert judgement, to continue historical trends and be in accordance with literature values.

### End-use good category splits
Region- and time-specific data on shares of good categories in steel consumption is very limited.
We therefore apply a function of these shares over gdp per capita to all regions, which we construct from three different data points from the literature, and a smooth interpolation in between.

### Reconciliation of scrap use
We read historical scrap use from literature data, but our model also predicts scrap use, via the outflow of the in-use stock model and rates for collection and recovery.
We use the literature data on scrap use to manually calibrate the parameters of the model, such that out model aligns with the dataset in historical years.
Since we only have reliable scrap use data for some world regions, we perform this calibration on a global scale, and for some selected regions individually.

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
The following table presents all exogenous parameters in the steel MFA with their respective dimensions and the sources of the respective input data. If no input data source is specified, the parameter is currently estimated based on expert judgement.

{% include-markdown "steel/definitions/parameters.md" %}
