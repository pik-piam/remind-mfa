from ODYM.odym.modules import dynamic_stock_model as dsm # import the dynamic stock model library
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

def predict(histdata,satlevel,sattime):
    t0 = 2008
    s0 = histdata[-1]

    # calculate gradient (a weighted average of the last four gradients is chosen to handle outliers)

    last = s0
    second = histdata[-2]
    third = histdata[-3]
    fourth = histdata[-4]
    fifth = histdata[-5]
    gradient=((last-second)*4+(second-third)*3+(third-fourth)*2+(fourth-fifth)*1)/10

    if(gradient<0.00001): # minimum value (there shouldn't be a negative gradient), value can be changed
        gradient=0.00001

    # calculate parameters for sigmoid saturation_curve

    A = satlevel
    B = sattime - 2008
    C = 0.99 * satlevel
    if (C<s0+gradient): # saturation is already reached and/or current gradient + current stock level is higher than saturation
        C=(s0+gradient)*1.00001 # new target saturation level is 0.002 % higher than current level, will result in de facto constant stock level
        A=(s0+gradient)*1.00002
    D = gradient
    E = D + s0
    L = log(A / C - 1)
    M = log(A / E - 1)

    x = (M * B - L) / (M - L)
    y = (M - L) / (B - 1)

    # sigmoid prediction

    prediction=np.zeros(92)
    for i in range(92):
        prediction[i]=A/(1+e**(-y*(i+1-x)))

    return np.append(histdata,prediction)



# load data
countries = ['Albania','Austria','Belgium-Luxembourg','Bulgaria', 'Czechoslovakia', 'Denmark', 'Finland', 'Fmr Yugoslavia',
             'France', 'Germany', 'Greece', 'Hungary', 'Iceland', 'Ireland', 'Italy','Malta', 'Netherlands', 'Norway',
             'Poland','Portugal', 'Romania','Spain','Sweden','Switzerland', 'United Kingdom']

categories = ['Transport', 'Machinery', 'Construction', 'Product']
time = np.array(range(1900,2101))

with open('data/stock_population_final.csv') as csv_file:
    data_reader = csv.reader(csv_file, delimiter=',')
    data = list(data_reader)

# initialise data dictionaries

datadic={}
for country in countries:
    datadic[country]={}

for date in data:
    nums = date[2:]
    floats = []
    for num in nums:
        floats.append(float(num))
    datadic[date[0]][date[1]]=np.array(floats)

# show European stock development

totalsteel=np.zeros(109)
totalPop=np.zeros(109)
for country in countries:
    totalPop+=datadic[country]["Population"][:109]
    for category in categories:
        totalsteel=totalsteel+datadic[country][category]*1000
print(totalPop)
plt.plot(np.array(list(range(1900,2009))),np.divide(totalsteel,totalPop))
plt.title("Europe Stock Development 1900-2008")
plt.show()

# create per capita data

for country in countries:
    countrydic = datadic[country]
    for category in categories:
        datadic[country][category]=np.divide(countrydic[category]*1000,countrydic["Population"][:109]) # calculates the per capita TONNES for the given category

# predict using sigmoid prediction

saturationLevelsPerCategory = [1.3, 0.9, 10, 0.6]
for country in countries:
    for i,category in enumerate(categories):
        datadic[country][category]=predict(datadic[country][category],saturationLevelsPerCategory[i],2030)

# multiply per capita predictions by population
totalPop = np.zeros(201)
for country in countries:
    for category in categories:
        datadic[country][category]=datadic[country][category]*datadic[country]['Population']
        totalPop+=datadic[country]['Population']
datadic['Population']=totalPop

# initiate ODYM Models

print("\nInitiate ODYM Models\n")
lifetimePerCategory=np.array([[20],[30],[75],[15]])
sdPerCategory=lifetimePerCategory*0.3
for country in countries:
    print(country)
    for i,category in enumerate(categories):
        SteelStock_DSM = dsm.DynamicStockModel(t = time,s=datadic[country][category],
                                               lt={'Type':'Normal','Mean':lifetimePerCategory[i],
                                                   'StdDev':sdPerCategory[i]})
        S_C, O_C, I = SteelStock_DSM.compute_stock_driven_model()
        O = SteelStock_DSM.compute_outflow_total()
        datadic[country][category]=SteelStock_DSM

# aggregate data for all of Europe

print("\nAggregate For Europe\n")
for i,category in enumerate(categories):
    stock_data = np.zeros(201)
    for country in countries:
        stock_data += datadic[country][category].s
    SteelStock_DSM = dsm.DynamicStockModel(t = time,s=stock_data,
                                               lt={'Type':'Normal','Mean':lifetimePerCategory[i],
                                                   'StdDev':sdPerCategory[i]})
    S_C, O_C, I = SteelStock_DSM.compute_stock_driven_model()
    O = SteelStock_DSM.compute_outflow_total()
    datadic[category]=SteelStock_DSM

# plot aggregate stocks/capita
plt.stackplot(time,[np.divide(datadic['Transport'].s,totalPop),np.divide(datadic['Machinery'].s,totalPop),np.divide(datadic['Construction'].s,totalPop),np.divide(datadic['Product'].s,totalPop)],
              labels=['Transport', 'Machinery', 'Construction', 'Product'])
plt.legend(loc=2, fontsize='large')
plt.title('European Steel Stocks per Capita(predicted, kT)')
plt.show()


# plot aggregate stocks

plt.stackplot(time,[datadic['Transport'].s,datadic['Machinery'].s,datadic['Construction'].s,datadic['Product'].s],
              labels=['Transport', 'Machinery', 'Construction', 'Product'])
plt.legend(loc=2, fontsize='large')
plt.title('European Steel Stocks (predicted, kT)')
plt.show()

# plot aggregate inflows

plt.stackplot(time,[datadic['Transport'].i,datadic['Machinery'].i,datadic['Construction'].i,datadic['Product'].i],
              labels=['Transport', 'Machinery', 'Construction', 'Product'])
plt.legend(loc=2, fontsize='large')
plt.title('European Steel Inflows (predicted, kT)')
plt.show()

# plot aggregate outflows

plt.stackplot(time,[datadic['Transport'].o,datadic['Machinery'].o,datadic['Construction'].o,datadic['Product'].o],
              labels=['Transport', 'Machinery', 'Construction', 'Product'])
plt.legend(loc=2, fontsize='large')
plt.title('European Steel Outflows (predicted, kT)')
plt.show()

# saveDSMs

for country in countries:
    for category in categories:
        filename="DSM"+category+country
        pickle.dump({filename: datadic[country][category]}, open("data/DSMcountries/"+filename+".p", "wb"))
for category in categories:
    filename="DSM"+category+"Europe"
    pickle.dump({filename: datadic[category]},open( "data/DSMcountries/"+filename+".p", "wb" ))

