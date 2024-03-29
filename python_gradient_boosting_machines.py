# -*- coding: utf-8 -*-
"""python-gradient-boosting-machines.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1Ziys30_NQbum0RBG4RwOW7wyt0ieQJW0

# Gradient Boosting Machines (GBMs) with XGBoost

Let's begin by installing the required libraries.
"""

#restart the kernel after installation
!pip install numpy pandas-profiling matplotlib seaborn --quiet

!pip install jovian opendatasets xgboost graphviz lightgbm scikit-learn xgboost lightgbm --upgrade --quiet

"""## Problem Statement

This tutorial takes a practical and coding-focused approach. We'll learn gradient boosting by applying it to a real-world dataset from the [Rossmann Store Sales](https://www.kaggle.com/c/rossmann-store-sales) competition on Kaggle:

> Rossmann operates over 3,000 drug stores in 7 European countries. Currently, Rossmann store managers are tasked with predicting their daily sales for up to six weeks in advance. Store sales are influenced by many factors, including promotions, competition, school and state holidays, seasonality, and locality.
>
>
> With thousands of individual managers predicting sales based on their unique circumstances, the accuracy of results can be quite varied. You are provided with historical sales data for 1,115 Rossmann stores. The task is to forecast the "Sales" column for the test set. Note that some stores in the dataset were temporarily closed for refurbishment.
>
> View and download the data here: https://www.kaggle.com/c/rossmann-store-sales/data
"""

!pip list | grep xgboost

"""## Downloading the Data

We can download the dataset from Kaggle directly within the Jupyter notebook using the `opendatasets` library. Make sure to [accept the competition rules](https://www.kaggle.com/c/rossmann-store-sales/rules) before executing the following cell.
"""

import os
import opendatasets as od
import pandas as pd
pd.set_option("display.max_columns", 120)
pd.set_option("display.max_rows", 120)

od.download('https://www.kaggle.com/c/rossmann-store-sales')

"""You'll be asked to provide your Kaggle credentials to download the data. Follow these instructions: http://bit.ly/kaggle-creds"""

os.listdir('rossmann-store-sales')

"""Let's load the data into Pandas dataframes."""

ross_df = pd.read_csv('./rossmann-store-sales/train.csv', low_memory=False)
store_df = pd.read_csv('./rossmann-store-sales/store.csv')
test_df = pd.read_csv('./rossmann-store-sales/test.csv')
submission_df = pd.read_csv('./rossmann-store-sales/sample_submission.csv')

ross_df

test_df

submission_df

store_df



"""Let's merge the information from `store_df` into `train_df` and `test_df`."""

merged_df = ross_df.merge(store_df, how='left', on='Store')
merged_test_df = test_df.merge(store_df, how='left', on='Store')

merged_df



merged_df.describe()

merged_df.corr()

"""Let's save our work before continuing.

## Preprocessing and Feature Engineering

Let's take a look at the available columns, and figure out if we can create new columns or apply any useful transformations.
"""

merged_df.info()

"""
### Date

First, let's convert `Date` to a `datetime` column and extract different parts of the date."""

def split_date(df):
    df['Date'] = pd.to_datetime(df['Date'])
    df['Year'] = df.Date.dt.year
    df['Month'] = df.Date.dt.month
    df['Day'] = df.Date.dt.day
    df['WeekOfYear'] = df.Date.dt.isocalendar().week

split_date(merged_df)
split_date(merged_test_df)

merged_df

"""### Store Open/Closed

Next, notice that the sales are zero whenever the store is closed.
"""

merged_df[merged_df.Open == 0].Sales

"""Instead of trying to model this relationship, it would be better to hard-code it in our predictions, and remove the rows where the store is closed. We won't remove any rows from the test set, since we need to make predictions for every row."""

merged_df = merged_df[merged_df.Open == 1].copy()

merged_df

"""### Competition

Next, we can use the columns `CompetitionOpenSince[Month/Year]` columns from `store_df` to compute the number of months for which a competitor has been open near the store.
"""

def comp_months(df):
    df['CompetitionOpen'] = 12 * (df.Year - df.CompetitionOpenSinceYear) + (df.Month - df.CompetitionOpenSinceMonth)
    df['CompetitionOpen'] = df['CompetitionOpen'].map(lambda x: 0 if x < 0 else x).fillna(0)

comp_months(merged_df)
comp_months(merged_test_df)

merged_df

"""Let's view the results of the new columns we've created."""

merged_df[['Date', 'CompetitionDistance', 'CompetitionOpenSinceYear', 'CompetitionOpenSinceMonth', 'CompetitionOpen']].sample(20)

"""### Additional Promotion

We can also add some additional columns to indicate how long a store has been running `Promo2` and whether a new round of `Promo2` starts in the current month.
"""

def check_promo_month(row):
    month2str = {1:'Jan', 2:'Feb', 3:'Mar', 4:'Apr', 5:'May', 6:'Jun',
                 7:'Jul', 8:'Aug', 9:'Sept', 10:'Oct', 11:'Nov', 12:'Dec'}
    try:
        months = (row['PromoInterval'] or '').split(',')
        if row['Promo2Open'] and month2str[row['Month']] in months:
            return 1
        else:
            return 0
    except Exception:
        return 0

def promo_cols(df):
    # Months since Promo2 was open
    df['Promo2Open'] = 12 * (df.Year - df.Promo2SinceYear) +  (df.WeekOfYear - df.Promo2SinceWeek)*7/30.5
    df['Promo2Open'] = df['Promo2Open'].map(lambda x: 0 if x < 0 else x).fillna(0) * df['Promo2']
    # Whether a new round of promotions was started in the current month
    df['IsPromo2Month'] = df.apply(check_promo_month, axis=1) * df['Promo2']

promo_cols(merged_df)
promo_cols(merged_test_df)

"""Let's view the results of the columns we've created."""

merged_df[['Date', 'Promo2', 'Promo2SinceYear', 'Promo2SinceWeek', 'PromoInterval', 'Promo2Open', 'IsPromo2Month']].sample(20)

merged_df.corr()

"""The features related to competition and promotion are now much more useful.

### Input and Target Columns

Let's select the columns that we'll use for training.
"""

merged_df.columns

input_cols = ['Store', 'DayOfWeek', 'Promo', 'StateHoliday', 'SchoolHoliday',
              'StoreType', 'Assortment', 'CompetitionDistance', 'CompetitionOpen',
              'Day', 'Month', 'Year', 'WeekOfYear',  'Promo2',
              'Promo2Open', 'IsPromo2Month']
target_col = 'Sales'

inputs = merged_df[input_cols].copy()
targets = merged_df[target_col].copy()

test_inputs = merged_test_df[input_cols].copy()

"""Let's also identify numeric and categorical columns. Note that we can treat binary categorical columns (0/1) as numeric columns."""

numeric_cols = ['Store', 'Promo', 'SchoolHoliday',
              'CompetitionDistance', 'CompetitionOpen', 'Promo2', 'Promo2Open', 'IsPromo2Month',
              'Day', 'Month', 'Year', 'WeekOfYear',  ]
categorical_cols = ['DayOfWeek', 'StateHoliday', 'StoreType', 'Assortment']

"""### Impute missing numerical data"""

inputs[numeric_cols].isna().sum()

test_inputs[numeric_cols].isna().sum()

"""Seems like competition distance is the only missing value, and we can simply fill it with the highest value (to indicate that competition is very far away)."""

max_distance = inputs.CompetitionDistance.max()

inputs['CompetitionDistance'].fillna(max_distance, inplace=True)
test_inputs['CompetitionDistance'].fillna(max_distance, inplace=True)

"""### Scale Numeric Values

Let's scale numeric values to the 0 to 1 range.
"""

from sklearn.preprocessing import MinMaxScaler
from sklearn.preprocessing import OneHotEncoder
from sklearn.preprocessing import StandardScaler

scaler = MinMaxScaler().fit(inputs[numeric_cols])

inputs[numeric_cols] = scaler.transform(inputs[numeric_cols])
test_inputs[numeric_cols] = scaler.transform(test_inputs[numeric_cols])

"""### Encode Categorical Columns

<img src="https://i.imgur.com/n8GuiOO.png" width="640">

Let's one-hot encode categorical columns.
"""

from sklearn.preprocessing import OneHotEncoder

encoder = OneHotEncoder(sparse=False, handle_unknown='ignore').fit(inputs[categorical_cols])
encoded_cols = list(encoder.get_feature_names_out(categorical_cols))

inputs[encoded_cols] = encoder.transform(inputs[categorical_cols])
test_inputs[encoded_cols] = encoder.transform(test_inputs[categorical_cols])

"""Finally, let's extract out all the numeric data for training."""

X = inputs[numeric_cols + encoded_cols]
X_test = test_inputs[numeric_cols + encoded_cols]

"""We haven't created a validation set yet, because we'll use K-fold cross validation.

# Lets Check Out The Linear Regvression for this
"""

x_df = X.copy()
x_df

y_df = targets.copy()
y_df

from sklearn.model_selection import train_test_split

# x_train, x_test , y_tarin , y_test = train_test_split(x_df , y_df , test_size = 0.1)




split_point = int(0.8 * len(x_df))  # Use 80% of data for training
x_train = x_df.iloc[:split_point]
x_test= x_df.iloc[split_point:]

sp = int(0.8 * len(y_df))
y_tarin = y_df.iloc[:split_point]
y_test= y_df.iloc[split_point:]

from sklearn.linear_model import LinearRegression

Model= LinearRegression()

Model.fit(x_train, y_tarin)

predit = Model.predict(x_test)

from sklearn.metrics import mean_squared_error

linearerror = mean_squared_error(y_test,predit )

"""## Lets Check out with the Decision tree regression"""

from sklearn.tree import DecisionTreeRegressor

treemodel= DecisionTreeRegressor()
treemodel.fit(x_train, y_tarin)

predict_y = treemodel.predict(x_test)

treeerror = mean_squared_error(y_test , predict_y )

print("linear_error: " ,  linearerror)
print("tree_error : ", treeerror)

treemodel2 = DecisionTreeRegressor(max_depth =200)
treemodel2.fit(x_train, y_tarin)

predict_y2 = treemodel2.predict(x_test)
treeerror2 = mean_squared_error(y_test , predict_y2 )

print("linear_error: " ,  linearerror)
print("tree_error :  ", treeerror2)

from sklearn.tree import DecisionTreeRegressor
from sklearn.metrics import mean_squared_error
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import MinMaxScaler
from sklearn.preprocessing import OneHotEncoder
from sklearn.preprocessing import StandardScaler

"""Let's save our work before continuing.

## Gradient Boosting

We're now ready to train our gradient boosting machine (GBM) model. Here's how a GBM model works:

1. The average value of the target column and uses as an initial prediction every input.
2. The residuals (difference) of the predictions with the targets are computed.
3. A decision tree of limited depth is trained to **predict just the residuals** for each input.
4. Predictions from the decision tree are scaled using a parameter called the learning rate (this prevents overfitting)
5. Scaled predictions for the tree are added to the previous predictions to obtain the new and improved predictions.
6. Steps 2 to 5 are repeated to create new decision trees, each of which is trained to predict just the residuals from the previous prediction.

The term "gradient" refers to the fact that each decision tree is trained with the purpose of reducing the loss from the previous iteration (similar to gradient descent). The term "boosting" refers the general technique of training new models to improve the results of an existing model.

> **EXERCISE**: Can you describe in your own words how a gradient boosting machine is different from a random forest?


For a mathematical explanation of gradient boosting, check out the following resources:

- [XGBoost Documentation](https://xgboost.readthedocs.io/en/latest/tutorials/model.html)
- [Video Tutorials on StatQuest](https://www.youtube.com/watch?v=3CC4N4z3GJc&list=PLblh5JKOoLUJjeXUvUE0maghNuY2_5fY6)

Here's a visual representation of gradient boosting:

![](https://miro.medium.com/max/560/1*85QHtH-49U7ozPpmA5cAaw.png)

### Training

To train a GBM, we can use the `XGBRegressor` class from the [`XGBoost`](https://xgboost.readthedocs.io/en/latest/) library.
"""

from xgboost import XGBRegressor

model = XGBRegressor(random_state=42, n_jobs=-1, n_estimators=20, max_depth=4)

"""Let's train the model using `model.fit`."""

# Commented out IPython magic to ensure Python compatibility.
# %%time
# model.fit(X, targets)

"""### Prediction

We can now make predictions and evaluate the model using `model.predict`.
"""

preds = model.predict(X)

preds

"""### Evaluation

Let's evaluate the predictions using RMSE error.
"""

from sklearn.metrics import mean_squared_error

def rmse(a, b):
    return mean_squared_error(a, b, squared=False)

rmse(preds, targets)



"""### Visualization

We can visualize individual trees using `plot_tree` (note: this requires the `graphviz` library to be installed).
"""

# Commented out IPython magic to ensure Python compatibility.
import matplotlib.pyplot as plt
from xgboost import plot_tree
from matplotlib.pylab import rcParams
# %matplotlib inline

rcParams['figure.figsize'] = 30,30

plot_tree(model, rankdir='LR', num_trees = 2);

plot_tree(model, rankdir='LR', num_trees=1);

plot_tree(model, rankdir='LR', num_trees=19);

"""Notice how the trees only compute residuals, and not the actual target value. We can also visualize the tree as text."""

trees = model.get_booster().get_dump()

len(trees)

print(trees[0])

"""### Feature importance

Just like decision trees and random forests, XGBoost also provides a feature importance score for each column in the input.
"""

importance_df = pd.DataFrame({
    'feature': X.columns,
    'importance': model.feature_importances_
}).sort_values('importance', ascending=False)

importance_df.head(10)

import seaborn as sns
plt.figure(figsize=(10,6))
plt.title('Feature Importance')
sns.barplot(data=importance_df.head(10), x='importance', y='feature');

"""Let's save our work before continuing.

## K Fold Cross Validation

Notice that we didn't create a validation set before training our XGBoost model. We'll use a different validation strategy this time, called K-fold cross validation ([source](https://vitalflux.com/k-fold-cross-validation-python-example/)):

![](https://vitalflux.com/wp-content/uploads/2020/08/Screenshot-2020-08-15-at-11.13.53-AM.png)

Scikit-learn provides utilities for performing K fold cross validation.
"""

from sklearn.model_selection import KFold

"""Let's define a helper function `train_and_evaluate` which trains a model the given parameters and returns the trained model, training error and validation error."""

def train_and_evaluate(X_train, train_targets, X_val, val_targets, **params):
    model = XGBRegressor(random_state=42, n_jobs=-1, **params)
    model.fit(X_train, train_targets)
    train_rmse = rmse(model.predict(X_train), train_targets)
    val_rmse = rmse(model.predict(X_val), val_targets)
    return model, train_rmse, val_rmse

"""Now, we can use the `KFold` utility to create the different training/validations splits and train a separate model for each fold."""

kfold = KFold(n_splits=5)

models = []

for train_idxs, val_idxs in kfold.split(X):
    X_train, train_targets = X.iloc[train_idxs], targets.iloc[train_idxs]
    X_val, val_targets = X.iloc[val_idxs], targets.iloc[val_idxs]
    model, train_rmse, val_rmse = train_and_evaluate(X_train,
                                                     train_targets,
                                                     X_val,
                                                     val_targets,
                                                     max_depth=4,
                                                     n_estimators=20)
    models.append(model)
    print('Train RMSE: {}, Validation RMSE: {}'.format(train_rmse, val_rmse))

"""Let's also define a function to average predictions from the 5 different models."""

import numpy as np

def predict_avg(models, inputs):
    return np.mean([model.predict(inputs) for model in models], axis=0)

preds = predict_avg(models, X)

preds

"""We can now use `predict_avg` to make predictions for the test set."""

model

"""Here's a helper function to test hyperparameters with K-fold cross validation."""

def test_params_kfold(n_splits, **params):
    train_rmses, val_rmses, models = [], [], []
    kfold = KFold(n_splits)
    for train_idxs, val_idxs in kfold.split(X):
        X_train, train_targets = X.iloc[train_idxs], targets.iloc[train_idxs]
        X_val, val_targets = X.iloc[val_idxs], targets.iloc[val_idxs]
        model, train_rmse, val_rmse = train_and_evaluate(X_train, train_targets, X_val, val_targets, **params)
        models.append(model)
        train_rmses.append(train_rmse)
        val_rmses.append(val_rmse)
    print('Train RMSE: {}, Validation RMSE: {}'.format(np.mean(train_rmses), np.mean(val_rmses)))
    return models

"""Since it may take a long time to perform 5-fold cross validation for each set of parameters we wish to try, we'll just pick a random 10% sample of the dataset as the validation set."""

from sklearn.model_selection import train_test_split

X_train, X_val, train_targets, val_targets = train_test_split(X, targets, test_size=0.1)

def test_params(**params):
    model = XGBRegressor(n_jobs=-1, random_state=42, **params)
    model.fit(X_train, train_targets)
    train_rmse = rmse(model.predict(X_train), train_targets)
    val_rmse = rmse(model.predict(X_val), val_targets)
    print('Train RMSE: {}, Validation RMSE: {}'.format(train_rmse, val_rmse))

"""#### `n_estimators`

The number of trees to be created. More trees = greater capacity of the model.

"""

test_params(n_estimators=10)

test_params(n_estimators=30)

test_params(n_estimators=100)

test_params(n_estimators=240)



"""#### `max_depth`

As you increase the max depth of each tree, the capacity of the tree increases and it can capture more information about the training set.
"""

test_params(max_depth=2)

test_params(max_depth=5)

test_params(max_depth=10)



"""#### `learning_rate`

The scaling factor to be applied to the prediction of each tree. A very high learning rate (close to 1) will lead to overfitting, and a low learning rate (close to 0) will lead to underfitting.
"""

test_params(n_estimators=50, learning_rate=0.01)

test_params(n_estimators=50, learning_rate=0.1)

test_params(n_estimators=50, learning_rate=0.3)

test_params(n_estimators=50, learning_rate=0.9)

test_params(n_estimators=50, learning_rate=0.99)





"""#### `booster`

Instead of using Decision Trees, XGBoost can also train a linear model for each iteration. This can be configured using `booster`.
"""

test_params(booster='gblinear')

"""Clearly, a linear model is not well suited for this dataset."""



"""## Putting it Together and Making Predictions

Let's train a final model on the entire training set with custom hyperparameters.
"""

model = XGBRegressor(n_jobs=-1, random_state=42, n_estimators=1000,
                     learning_rate=0.2, max_depth=10, subsample=0.9,
                     colsample_bytree=0.7)

# Commented out IPython magic to ensure Python compatibility.
# %%time
# model.fit(X, targets)

"""Now that the model is trained, we can make predictions on the test set."""

test_preds = model.predict(X_test)

"""Let's add the predictions into `submission_df`."""

submission_df['Sales']  = test_preds

"""Recall, however, if if the store is not open, then the sales must be 0. Thus, wherever the value of `Open` in the test set is 0, we can set the sales to 0. Also, there some missing values for `Open` in the test set. We'll replace them with 1 (open)."""

test_df.Open.isna().sum()

submission_df['Sales'] = submission_df['Sales'] * test_df.Open.fillna(1.)

submission_df

"""We can now save the predictions as a CSV file."""

submission_df.to_csv('submission.csv', index=None)

from IPython.display import FileLink

# Doesn't work on Colab, use the file browser instead.
FileLink('submission.csv')

"""We can now make a submission on this page and check our score: https://www.kaggle.com/c/rossmann-store-sales/submit

![](https://i.imgur.com/bQ0lpSJ.png)
"""









