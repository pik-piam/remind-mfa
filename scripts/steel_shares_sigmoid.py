# %%
import plotly.express as px
import pandas as pd
import numpy as np

# you have this already
names = ['Construction', 'Machinery', 'Products', 'Transport']
s_ind = np.array([0.47, 0.32, 0.10, 0.11])
s_usa = np.array([0.47, 0.10, 0.13, 0.30])

# please get exact values for this from your data
gdppc_ind = 320
gdppc_usa = 40000

# this is just the values we plot over
log_gdppc = np.linspace(-30, 30, 300)
gdppc = 10. ** log_gdppc


# this is the core of the calculation: sigmoid over gdppc
# -3 and +3 are x-values where the sigmoid has almost reached its limits (0 and 1)
def alpha(gdppc):
    x = -3. + 6. * (np.log(gdppc) - np.log(gdppc_ind)) / (np.log(gdppc_usa) - np.log(gdppc_ind))
    return 1. / (1. + np.exp(-x))


a = alpha(gdppc)

# stretch a such that it is 0 at GDPPC_IND and 1 at GDPPC_USA (actually overshooting/extrpolating their values slightly)
a_ind = alpha(gdppc_ind)
a_usa = alpha(gdppc_usa)
a = (a - a_ind) / (a_usa - a_ind)

# s = a*S_USA + (1-a)*S_IND
# with correct numpy dimensions
s = a[:, np.newaxis] * s_usa + (1 - a[:, np.newaxis]) * s_ind

df = pd.DataFrame(s, columns=names)
df['gdppc'] = gdppc
fig = px.line(df, x='gdppc', y=names)
# vertcial lines at GDPPC_IND and GDPPC_USA
fig.add_vline(x=gdppc_ind, line_dash="dash", line_color="green")
fig.add_vline(x=gdppc_usa, line_dash="dash", line_color="red")
fig.update_layout(xaxis_type="log")
fig.show()

a = 0
# %%
