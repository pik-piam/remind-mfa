# %% RECOVERY RATE
import numpy as np
from matplotlib import pyplot as plt

ela = -1
r0 = 0.85
p0 = 1.
r_free = 0.3


def r(p):
    a = 1 / (((1 - r0) / (1 - r_free))**(1 / ela) - 1)
    return (1 - (1 - r0) * ((p / p0 + a) / (1 + a))**ela)


plt.figure()
p = np.arange(0., 3., 0.01)
plt.plot(p, r(p))
plt.title('Recovery rate of scrap at factor of initial scrap price')
plt.xlabel('Factor of initial scrap price')
plt.ylabel('Recovery rate of scrap')
ps = np.array([0., p0, 2. * p0])
plt.scatter(ps, r(ps))
plt.show()


# %% SCRAP SHARE IN PRODUCTION
import numpy as np
from matplotlib import pyplot as plt

ela = -1.2
r0 = 0.85
p0 = 1.
r_free = 0.50


def r(p):
    a = 1 / (((1 - r0) / (1 - r_free))**(1 / ela) - 1)
    return (1 - (1 - r0) * ((p / p0 + a) / (1 + a))**ela)


plt.figure()
p = np.arange(0., 3., 0.01)
plt.plot(p, r(p))
plt.title('Scrap share in scaler at factor of initial dissassembly price')
plt.xlabel('Factor of initial dissassmbly price')
plt.ylabel('Scrap share in scaler')
ps = np.array([0., p0, 2. * p0])
plt.scatter(ps, r(ps))
plt.show()



# %%
