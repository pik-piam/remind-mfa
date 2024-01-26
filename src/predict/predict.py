from src.predict.duerrwaechter_prediction import predict_duerrwaechter
from src.tools.config import cfg
from src.tools.tools import transform_per_capita_np


def predict_stocks(historic_stocks,
                   strategy=cfg.curve_strategy):
    """
    Calculates In-use steel stock per capita data based on GDP pC using approach given in
    config file (e.g. Pauliuk or Pehl).
    Optionally creates plot to show predict for Germany.
    :return: Steel data for the years 1900-2100, so BOTH present and past using predict
    approach given in config file.
    """
    historic_stocks_pc = transform_per_capita_np(arr=historic_stocks, total_from_per_capita=False)

    if strategy == "Duerrwaechter":
        stocks_pc = predict_duerrwaechter(historic_stocks_pc)
    else:
        raise RuntimeError(f"Prediction strategy {strategy} is not defined. "
                           f"It needs to be 'Duerrwaechter'.")

    stocks = transform_per_capita_np(arr=stocks_pc, total_from_per_capita=True)

    return stocks


def test():
    pass


if __name__ == "__main__":
    test()
