# Cement MFA
## Methodology

### Stock extrapolation
The stock extrapolation method for cement resembles largely the methodology represented in the [Model overview](methodology.md). The stock projection was obtained by fitting a logistic funtion on the logarithm of GDP, independently for each region and stock type. To decrease the degrees of freedom, function parameters were set or bounded. Saturation levels were estimated from historic trends and expert judgement. Stock expansion rates in low-stock regions are limited through an upper bound set as the observed stock growth rate of China. Similarly, the point where the logistic function reaches 50 percent of saturation is constrained through a lower bound informed by historic Chinese stock expansion dynamics.

## Processes
The following table lists the processes that are modelled in the cement MFA.

{% include-markdown "cement/definitions/processes.md" %}

## Dimensions
The following table presents the dimensions over which parameters and variables (stocks and flows incl. trades) are defined in the cement MFA.

{% include-markdown "cement/definitions/dimensions.md" %}

## Stocks
The following table presents the processes that are modelled as stocks in the cement MFA with their respective dimensions and the lifetime model that is employed. The historic_cement_in_use stock represents the weight of cement in the historic in-use stock. The in_use stock represents the weight of the final product, i.e., the weight of both concrete and mortar. Cement contents of this stock can be inferred by applying a cement-to-product ratio.

{% include-markdown "cement/definitions/stocks.md" %}

## Flows
The following table presents all flows in the cement MFA with their respective dimensions and the processes that they connect.

{% include-markdown "cement/definitions/flows.md" %}

## Parameters
The following table presents all exogenous parameters in the cement MFA with their respective dimensions and the sources of the respective input data.

{% include-markdown "cement/definitions/parameters.md" %}
