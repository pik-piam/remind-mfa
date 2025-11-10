# Plastic MFA
## Methodology

## Processes
The following table lists the processes that are modelled in the plastics MFA.

{!../data/plastics/output/export/definitions/processes.md!}

## Dimensions
The following table presents the dimensions over which parameters and variables (stocks and flows incl. trades) are defined in the plastics MFA.

{!../data/plastics/output/export/definitions/dimensions.md!}

## Stocks
The following table presents the processes that are modelled as stocks in the plastics MFA with their respective dimensions and the lifetime model that is employed. We use an auxiliary stock for the stock extrapolation with only the dimensions that are regressed separately (r, g) to save dimensions and computation time. The auxiliary stock is computed using a dynamic stock model. The results are then transferred to the higher-dimensional in-use-stock in the MFA system by multiplying stock, inflow and outflow with the parameters "material shares in goods" and "carbon content materials". This stock is modelled as a simple flow driven stock.

{!../data/plastics/output/export/definitions/stocks.md!}

## Flows
The following table presents all flows in the plastics MFA with their respective dimensions and the processes that they connect.

{!../data/plastics/output/export/definitions/flows.md!}

Flows that enter or leave markets are the exports and imports of the trades listed in the following table.

{!../data/plastics/output/export/definitions/trades.md!}

## Parameters
The following table presents all exogenous parameters in the plastics MFA with their respective dimensions.

{!../data/plastics/output/export/definitions/parameters.md!}