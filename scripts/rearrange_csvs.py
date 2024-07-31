import pandas as pd
import os

dir_path = os.path.join('data', 'steel', 'input', 'datasets')
path = os.path.join(dir_path, '../data/steel/input/datasets/old_good_to_intermediate_distribution.csv')

df = pd.read_csv(path)
df = df.set_index('Intermediate')
df = df.sort_index(axis=1)
df = df.sort_index(axis=0)
df = df.transpose()
df = df.stack()
print(df)
#df.to_csv(os.path.join(dir_path, 'new_good_to_intermediate_distribution.csv'))
