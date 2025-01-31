import pickle
import numpy as np


old_path = "data/steel/output_old/export/mfa.pickle"
new_path = "data/steel/output/export/mfa.pickle"

old = pickle.load(open(old_path, "rb"))
new = pickle.load(open(new_path, "rb"))

for flow in old["flows"]:
    diff = old["flows"][flow] - new["flows"][flow]
    if np.max(np.abs(diff)) > 1.E-10:
        print(flow)
        print(np.max(np.abs(diff)))
