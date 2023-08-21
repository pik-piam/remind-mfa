# %% RECOVERY RATE
import numpy as np
from matplotlib import pyplot as plt

ela = -1.
r0 = 0.85
p0 = 1.
r_free = 0.


def r(p):
    a = 1 / (((1 - r0) / (1 - r_free))**(1 / ela) - 1)
    return (1 - (1 - r0) * ((p / p0 + a) / (1 + a))**ela)


plt.figure()
p = np.arange(0., 3., 0.01)
plt.plot(p, r(p))
ps = np.array([0., p0, 2. * p0])
plt.scatter(ps, r(ps))
plt.show()


# %% SCRAP SHARE IN PRODUCTION
import numpy as np
from matplotlib import pyplot as plt

ela = -1.
r0 = 0.85
p0 = 1.
r_free = 0.


def r(p):
    a = 1 / (((1 - r0) / (1 - r_free))**(1 / ela) - 1)
    return (1 - (1 - r0) * ((p / p0 + a) / (1 + a))**ela)


plt.figure()
p = np.arange(0., 3., 0.01)
plt.plot(p, r(p))
ps = np.array([0., p0, 2. * p0])
plt.scatter(ps, r(ps))
plt.show()



# %%
