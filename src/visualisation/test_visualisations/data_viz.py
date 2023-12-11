from ODYM.odym.modules import dynamic_stock_model as dsm  # import the dynamic stock model library
import sys
import os
import numpy as np
import csv
import pandas as pd
import matplotlib.pyplot as plt
import pickle
import openpyxl
import pylab
from math import exp, e, log
from sympy import symbols, Eq, solve


def test_country_predictions(country):
    plt.rcParams["figure.figsize"] = [7.50, 3.50]
    plt.rcParams["figure.autolayout"] = True
    t = np.arange(1900, 2101, 1)
    fig, ax1 = plt.subplots()
    color = 'red'
    data1 = datadic[country]["Transport pC"]
    data2 = datadic[country]["Construction pC"]
    ax1.set_xlabel('time (years)')
    ax1.set_ylabel('Transportation (kT)', color=color)
    ax1.plot(t, data1, color=color)
    ax1.tick_params(axis='y', labelcolor=color)
    ax2 = ax1.twinx()

    color = 'blue'
    ax2.set_ylabel('Construction (kT)', color=color)
    ax2.plot(t, data2, color=color)
    ax2.tick_params(axis='y', labelcolor=color)

    plt.title('Steel Stock Prediction pC' + country)

    plt.show()


# load data
countries = ['Albania', 'Austria', 'Belgium-Luxembourg', 'Bulgaria', 'Czechoslovakia', 'Denmark', 'Finland',
             'Fmr Yugoslavia',
             'France', 'Germany', 'Greece', 'Hungary', 'Iceland', 'Ireland', 'Italy', 'Malta', 'Netherlands', 'Norway',
             'Poland', 'Portugal', 'Romania', 'Spain', 'Sweden', 'Switzerland', 'United Kingdom']

categories = ['Transport', 'Machinery', 'Construction', 'Product']
time = np.array(range(1900, 2101))

with open('data/stock_population_final.csv') as csv_file:
    data_reader = csv.reader(csv_file, delimiter=',')
    data = list(data_reader)

# initialise data dictionaries

datadic = {}
for country in countries:
    datadic[country] = {}

for date in data:
    nums = date[2:]
    floats = []
    for num in nums:
        floats.append(float(num))
    datadic[date[0]][date[1]] = np.array(floats)

# create per capita data

for country in countries:
    countrydic = datadic[country]
    for category in categories:
        datadic[country][category] = np.divide(countrydic[category] * 1000, countrydic["Population"][
                                                                            :109])  # calculates the per capita TONNES for the given category

# possible predict test
# if country=="Germany":
#    test_country_predictions(country)
countries = ['Albania', 'Austria', 'Bulgaria', 'Denmark', 'Finland', 'Czechoslovakia', 'Belgium-Luxembourg',
             'Fmr Yugoslavia',
             'Germany', 'Greece', 'Hungary', 'Iceland', 'Ireland', 'Italy', 'Norway', 'Malta',
             'Poland', 'Portugal', 'Romania', 'Spain', 'Sweden', 'Switzerland', 'United Kingdom']

aggregatedTransport = []
aggregatedMachinery = []
aggregatedConstruction = []
aggregatedProduct = []
aggregatedGDPPC = []
sumTransport = np.zeros(59)
sumMachinery = np.zeros(59)
sumConstruction = np.zeros(59)
sumProduct = np.zeros(59)
sumGDP = np.zeros(59)
sumPop = np.zeros(59)
for country in countries:
    print(country)
    plt.plot(datadic[country]["GDP"][50:109], datadic[country]["Product"][50:109], 'b.')
    plt.title(country)
    plt.show()
    sumGDP += datadic[country]["GDP"][50:109] * datadic[country]["Population"][50:109]
    sumTransport += datadic[country]["Transport"][50:109] * datadic[country]["Population"][50:109]
    sumMachinery += datadic[country]["Machinery"][50:109] * datadic[country]["Population"][50:109]
    sumConstruction += datadic[country]["Construction"][50:109] * datadic[country]["Population"][50:109]
    sumProduct += datadic[country]["Product"][50:109] * datadic[country]["Population"][50:109]
    sumPop += datadic[country]["Population"][50:109]
    aggregatedTransport = np.concatenate((aggregatedTransport, datadic[country]["Transport"][50:109]), axis=None)
    aggregatedMachinery = np.concatenate((aggregatedMachinery, datadic[country]["Machinery"][50:109]), axis=None)
    aggregatedConstruction = np.concatenate((aggregatedConstruction, datadic[country]["Construction"][50:109]),
                                            axis=None)
    aggregatedProduct = np.concatenate((aggregatedProduct, datadic[country]["Product"][50:109]), axis=None)
    aggregatedGDPPC = np.concatenate((aggregatedGDPPC, datadic[country]["GDP"][50:109]), axis=None)
plt.plot(aggregatedGDPPC, aggregatedTransport, 'b.')
plt.xlabel("GDP pC (USD 2005)")
plt.ylabel("Steel Stock pC (kT) - Transport")
plt.title("Aggregated Transport")
plt.show()
plt.plot(aggregatedGDPPC, aggregatedMachinery, 'b.')
plt.xlabel("GDP pC (USD 2005)")
plt.ylabel("Steel Stock pC (kT) - Machinery")
plt.title("Aggregated Machienry")
plt.show()
plt.plot(aggregatedGDPPC, aggregatedConstruction, 'b.')
plt.xlabel("GDP pC (USD 2005)")
plt.ylabel("Steel Stock pC (kT) - Construction")
plt.title("Aggregated Construction")
plt.show()
plt.plot(aggregatedGDPPC, aggregatedProduct, 'b.')
plt.xlabel("GDP pC (USD 2005)")
plt.ylabel("Steel Stock pC (kT) - Product")
plt.title("Aggregated Product")
plt.show()
aggregatedTotal = aggregatedProduct + aggregatedTransport + aggregatedConstruction + aggregatedMachinery
plt.plot(aggregatedGDPPC, aggregatedTotal, 'b.')
plt.xlabel("GDP pC (USD 2005)")
plt.ylabel("Steel Stock pC (kT) - Total")
plt.title("Aggregated Total")
plt.show()
sumTotal = sumTransport + sumConstruction + sumMachinery + sumProduct
sumTotal = np.divide(sumTotal, sumPop)
sumTransport = np.divide(sumTransport, sumPop)
sumConstruction = np.divide(sumConstruction, sumPop)
sumMachinery = np.divide(sumMachinery, sumPop)
sumProduct = np.divide(sumProduct, sumPop)
sumGDP = np.divide(sumGDP, sumPop)
plt.plot(sumGDP, sumTransport, 'b.')
plt.xlabel("GDP pC (USD 2005)")
plt.ylabel("Steel Stock pC (kT) - Transport")
plt.title("Europe - Steel in Transport")
plt.show()
plt.plot(sumGDP, sumConstruction, 'b.')
plt.xlabel("GDP pC (USD 2005)")
plt.ylabel("Steel Stock pC (kT) - Construction")
plt.title("Europe - Steel in Construction")
plt.show()
plt.plot(sumGDP, sumMachinery, 'b.')
plt.xlabel("GDP pC (USD 2005)")
plt.ylabel("Steel Stock pC (kT) - Machinery")
plt.title("Europe - Steel in Machinery")
plt.show()
plt.plot(sumGDP, sumProduct, 'b.')
plt.xlabel("GDP pC (USD 2005)")
plt.ylabel("Steel Stock pC (kT) - Product")
plt.title("Europe - Steel in Product")
plt.show()
plt.plot(sumGDP, sumTotal, 'b.')
plt.xlabel("GDP pC (USD 2005)")
plt.ylabel("Steel Stock pC (kT) - Total")
plt.title("Europe - Steel in Total")
plt.show()
