import os
import csv
from src.tools.config import cfg


def get_cullen_fabrication_yield():
    cullen_path = os.path.join(cfg.data_path, 'original', 'cullen', 'cullen_fabrication_yield_matrix.csv')
    with open(cullen_path) as csv_file:
        cullen_reader = csv.reader(csv_file, delimiter=',')
        cullen_list = list(cullen_reader)
        fabrication_yield = [float(line[1]) for line in cullen_list[1:]]
    return fabrication_yield


def get_wittig_distributions():
    wittig_path = os.path.join(cfg.data_path, 'original', 'Wittig', 'Wittig_matrix.csv')
    with open(wittig_path) as csv_file:
        wittig_reader = csv.reader(csv_file, delimiter=',')
        wittig_list = list(wittig_reader)
        use_recycling_params = [[float(num) for num in line[1:-1]] for line in wittig_list[1:]]
        recycling_usable_params = [float(line[-1]) for line in wittig_list[1:]]

    return use_recycling_params, recycling_usable_params


def _test():
    use_recycling_params, recycling_usable_params = get_wittig_distributions()
    fabrication_yield = get_cullen_fabrication_yield()

    print(f'Use-Recycling-Distribution: {use_recycling_params}')
    print(f'Recycling-Usable-Distribution: {recycling_usable_params}')
    print(f'Fabrication_Yield: {fabrication_yield}')


if __name__ == '__main__':
    _test()
