import matplotlib.pyplot as plt
import src.model.mfa_all_regions as mfa_all_regions
import src.read_data.read_IMF_gdp as gdp_data
import src.read_data.read_USGS_prices as price_data
import src.read_data.read_WorldSteel_trade as trade_data


REGIONS = ['CAZ', 'CHA', 'EUR', 'IND', 'JPN', 'LAM', 'MEA', 'NEU', 'OAS', 'REF', 'SSA', 'USA']
main_model = mfa_all_regions.load()
gdp_dict = gdp_data.load()
price_dict = price_data.load()
trade_dict = trade_data.load()

plt.plot(gdp_dict['Total'][34:110], price_dict['Steel'][34:110],'b.')
plt.plot(gdp_dict['Total'][34:110], price_dict['Scrap'][34:110],'r.')
plt.legend(['Steel','Scrap'])
plt.xlabel("GDP ($ 2008)")
plt.ylabel("Steel price ($ 1998)")
plt.title("Steel prices in relation to World GDP")
plt.show()

plt.plot(gdp_dict['USA']['Total'][34:110], price_dict['Steel'][34:110],'b.')
plt.plot(gdp_dict['USA']['Total'][34:110], price_dict['Scrap'][34:110],'r.')
plt.legend(['Steel','Scrap'])
plt.xlabel("GDP ($ 2008)")
plt.ylabel("Steel price ($ 1998)")
plt.title("Steel prices in relation to US GDP")
plt.show()

plt.plot(range(1934,2010), price_dict['Steel'][34:110],'b-')
plt.plot(range(1934,2010), price_dict['Scrap'][34:110],'r-')
plt.legend(['Steel','Scrap'])
plt.xlabel("time (y)")
plt.ylabel("Steel price ($ 1998)")
plt.title("Steel prices over time")
plt.show()

