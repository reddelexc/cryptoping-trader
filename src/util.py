import traceback
import requests
import json
import time
import gc

from threading import Thread

from .constants import garbage_cleaning_period


class PoolObject:
    def __init__(self):
        self.pool = None
        self.available = False

    def set_pool(self, pool):
        self.pool = pool


class GarbageCleanerThread(Thread):
    def __init__(self, bot):
        Thread.__init__(self)
        self.bot = bot

    def run(self):
        while True:
            gc.collect()
            time.sleep(garbage_cleaning_period)


def yobit_err(value):
    if value == 'Yobit':
        return 'YoBit'
    else:
        return value


def form_traceback(exc):
    trace = []
    for line in traceback.extract_tb(exc.__traceback__, limit=4096):
        trace.append(str(line))
    trace.append(str(exc))
    trace_str = '\n'.join(trace)
    return trace_str


def get_btc_price(date=None):
    if date is not None:
        date = str(date)
        url = 'https://api.coindesk.com/v1/bpi/historical/close.json?start=' + date + '&end=' + date
        resp = requests.get(url)
        price = json.loads(resp.text)['bpi'][date]
        resp.close()
        return price
    else:
        url = 'https://api.coindesk.com/v1/bpi/currentprice.json'
        resp = requests.get(url)
        price = json.loads(resp.text)['bpi']['USD']['rate_float']
        resp.close()
        return price
