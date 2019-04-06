import os
import gc
import time
import pandas as pd
import numpy as np

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, median_absolute_error
from sklearn.externals import joblib
from datetime import datetime
from threading import RLock, Thread

from .util import PoolObject, yobit_err, form_traceback
from .constants import predictor_main_cols, predictor_target_col, predictor_dataset, \
    predictor_dummy_cols, trained_model, learning_period

lock = RLock()


class Predictor(PoolObject):
    def __init__(self):
        PoolObject.__init__(self)

        self.dummies = None
        self.model = None
        self.model_date = None
        self.metrics = None
        self.load_stuff()

        self.data = None
        self.train_data = None
        self.val_data = None
        self.available = True

        print('predictor: started')

    def get_report(self):
        report = '    - Model last training date:\n'
        report += '        * {0}\n'.format(self.model_date)
        report += '    - Model metrics:\n'
        if self.metrics is None:
            report += '        * None\n'
            return report
        for k, v in self.metrics.items():
            if k == 'cols':
                report += '        * {0}:\n'.format(k)
                for token in v.split(','):
                    report += '            > {0}\n'.format(token)
            else:
                report += '        * {0}: {1:.2f}\n'.format(k, v)
        return report

    def learn(self):
        self.read_and_prepare_data()
        self.train()

    def predict(self, signal):
        self.data = pd.DataFrame(signal, index=[0])

        if self.model is None:
            self.load_stuff()
        self.read_and_prepare_data(to_predict=True)

        data_use_cols = self.data[predictor_main_cols]
        data_dummied = data_use_cols.reindex(columns=self.dummies, fill_value=0)
        data_dummied.pop(predictor_target_col)
        x = data_dummied

        preds = self.model.predict(x)
        return preds[0]

    def read_and_prepare_data(self, to_predict=False):
        if not to_predict:
            self.data = pd.read_csv(predictor_dataset)
            self.data = self.data[self.data['1h_max'].notnull()]
            train_size = int(self.data.shape[0] * 0.75)
            self.data = self.data.iloc[-train_size:].reset_index(drop=True)

        self.data['date'] = pd.to_datetime(self.data['date'], format='%Y-%m-%d %H:%M:%S')
        self.data['year'] = self.data['date'].apply(lambda d: d.year)
        self.data['month'] = self.data['date'].apply(lambda d: d.month)
        self.data['day'] = self.data['date'].apply(lambda d: d.day)
        self.data['hour'] = self.data['date'].apply(lambda d: d.hour)
        self.data['minute'] = self.data['date'].apply(lambda d: d.minute)
        self.data['exchange'] = self.data['exchange'].apply(yobit_err)
        self.data['1h_per'] = (self.data['1h_max'] / self.data['price_btc'] - 1) * 100
        self.data['6h_per'] = (self.data['6h_max'] / self.data['price_btc'] - 1) * 100
        self.data['24h_per'] = (self.data['24h_max'] / self.data['price_btc'] - 1) * 100
        self.data['48h_per'] = (self.data['48h_max'] / self.data['price_btc'] - 1) * 100
        self.data['7d_per'] = (self.data['7d_max'] / self.data['price_btc'] - 1) * 100

        if not to_predict:
            last_index = self.data.shape[0] - 1
            last_day = self.data.iloc[-1]['day']

            while self.data.iloc[last_index]['day'] == last_day:
                last_index -= 1

            val_end_index = last_index + 1
            last_day = self.data.iloc[last_index]['day']

            while self.data.iloc[last_index]['day'] == last_day:
                last_index -= 1

            val_start_index = last_index + 1

            self.train_data = self.data.iloc[:val_start_index].reset_index(drop=True)
            self.val_data = self.data.iloc[val_start_index:val_end_index].reset_index(drop=True)

    def train(self):
        train_data_use_cols = self.train_data[predictor_main_cols]
        val_data_use_cols = self.val_data[predictor_main_cols]

        train_data_dummied = pd.get_dummies(train_data_use_cols, columns=predictor_dummy_cols)
        val_data_dummied = val_data_use_cols.reindex(columns=train_data_dummied.columns, fill_value=0)

        train_y = train_data_dummied.pop(predictor_target_col)
        train_x = train_data_dummied

        test_y = val_data_dummied.pop(predictor_target_col)
        test_x = val_data_dummied

        self.pool['bot'].send(['Predictor: started training for metrics'])
        val_model = RandomForestRegressor(n_estimators=100, random_state=100)
        val_model.fit(train_x, train_y)
        self.metrics = Predictor.get_metrics(predictor_main_cols, test_y, val_model.predict(test_x))
        self.dump_metrics()

        self.train_data = None
        self.val_data = None
        gc.collect()

        self.pool['bot'].send(['Predictor: finished training for metrics'])

        data_use_cols = self.data[predictor_main_cols]
        data_dummied = pd.get_dummies(data_use_cols, columns=predictor_dummy_cols)
        self.dummies = data_dummied.columns

        train_y = data_dummied.pop(predictor_target_col)
        train_x = data_dummied

        self.pool['bot'].send(['Predictor: started training for real'])
        model = RandomForestRegressor(n_estimators=100, random_state=100)
        model.fit(train_x, train_y)
        self.model = model
        self.model_date = datetime.utcnow()
        self.dump_stuff()

        self.model = None
        self.dummies = None
        self.data = None
        gc.collect()

        self.pool['bot'].send(['Predictor: finished training for real'])

    def dump_stuff(self):
        with lock:
            self.available = False
        if not os.path.exists(trained_model):
            os.makedirs(trained_model)
        joblib.dump(self.dummies, os.path.join(trained_model, 'dummies'))
        joblib.dump(self.model, os.path.join(trained_model, 'model'))
        joblib.dump(self.model_date, os.path.join(trained_model, 'model_date'))
        with lock:
            self.available = True

    def dump_metrics(self):
        with lock:
            self.available = False
        if not os.path.exists(trained_model):
            os.makedirs(trained_model)
        joblib.dump(self.metrics, os.path.join(trained_model, 'metrics'))
        with lock:
            self.available = True

    def load_stuff(self):
        if not os.path.exists(trained_model):
            return
        self.dummies = joblib.load(os.path.join(trained_model, 'dummies'))
        self.model = joblib.load(os.path.join(trained_model, 'model'))
        self.model_date = joblib.load(os.path.join(trained_model, 'model_date'))
        self.metrics = joblib.load(os.path.join(trained_model, 'metrics'))

    @staticmethod
    def get_metrics(cols, real, preds):
        dev_1 = 0
        dev_5 = 0
        dev_10 = 0
        less_pred = 0
        more_pred = 0
        length = len(real)

        real = real.values
        for i in range(len(real)):
            if preds[i] >= real[i]:
                more_pred += 1
            if preds[i] < real[i]:
                less_pred += 1
            if abs(real[i] - preds[i]) <= 1:
                dev_1 += 1
            if abs(real[i] - preds[i]) <= 5:
                dev_5 += 1
            if abs(real[i] - preds[i]) <= 10:
                dev_10 += 1

        metrics = {
            'cols': ', '.join(cols),
            'real_mean': real.mean(),
            'real_median': np.median(real),
            'real_75_percentile': np.percentile(real, 75),
            'preds_mean': preds.mean(),
            'preds_median': np.median(preds),
            'preds_75_percentile': np.percentile(preds, 75),
            'mean_deviation': mean_absolute_error(real, preds),
            'median_deviation': median_absolute_error(real, preds),
            'deviation <= 1%': dev_1 / length,
            'deviation <= 5%': dev_5 / length,
            'deviation <= 10%': dev_10 / length,
            'pred < real': less_pred / length,
            'pred >= real': more_pred / length
        }

        return metrics


class PredictorLearnThread(Thread):
    def __init__(self, predictor, client, bot):
        Thread.__init__(self)
        self.predictor = predictor
        self.client = client
        self.bot = bot

    def run(self):
        while True:
            try:
                self.bot.send(['Updating dataset...'])
                self.client.update_dataset()
                self.bot.send(['Dataset updated'])

                self.bot.send(['Completing dataset...'])
                self.client.complete_dataset()
                self.bot.send(['Dataset completed'])

                self.predictor.learn()
            except Exception as exc:
                self.bot.send(['Something wrong happened:', form_traceback(exc)])
            time.sleep(learning_period)
