import numpy as np
from matplotlib import pyplot as plt
# add simson to path
import sys
sys.path.append("../simson")

from simson.common.data_blending import blending_factor

types = [
    "linear",
    "sigmoid3",
    "sigmoid4",
    "extrapol_sigmoid3",
    "extrapol_sigmoid4",
    "clamped_sigmoid3",
    "clamped_sigmoid4",
    "hermite",
    "quintic",
    "poly_mix",
    "converge_quadratic",
]

x = np.linspace(-1, 2, 1000)
plt.figure()
for type in types:
    plt.plot(x, blending_factor(x, type), label=type)
plt.legend()
plt.show()

