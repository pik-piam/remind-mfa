import pandas as pd
import numpy as np

data = range(1900, 2023)
data = np.array(data)
data = ['BOF', 'EAF']
data = pd.DataFrame(data)
data.to_csv('data/steel/input/dimensions/production.csv', header=False, index=False)
