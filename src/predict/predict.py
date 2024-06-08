import numpy as np
from src.predict.duerrwaechter_prediction import predict_duerrwaechter
from src.tools.config import cfg
from src.read_data.load_data import load_data


def predict_stocks(historic_stocks,
                   strategy=cfg.curve_strategy):
    """
    Calculates In-use steel stock per capita data based on GDP pC using approach given in
    config file (e.g. Pauliuk or Pehl).
    Optionally creates plot to show predict for Germany.
    :return: Steel data for the years 1900-2100, so BOTH present and past using predict
    approach given in config file.
    """

    # transform to per capita
    pop = load_data('population')
    historic_pop = pop[:cfg.n_historic_years, :]
    historic_stocks_pc = np.einsum(f'trc,tr->trc', historic_stocks, 1./historic_pop)

    if strategy == "Duerrwaechter":
        stocks_pc = predict_duerrwaechter(historic_stocks_pc)
    else:
        raise RuntimeError(f"Prediction strategy {strategy} is not defined. "
                           f"It needs to be 'Duerrwaechter'.")

    # transform back to total stocks
    stocks = np.einsum(f'trc,tr->trc', stocks_pc, pop)

    return stocks


def test():
    pass


if __name__ == "__main__":
    test()
