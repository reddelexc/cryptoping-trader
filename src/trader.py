import os
import json
import time
import ccxt

from xml.etree import ElementTree
from threading import RLock, Thread
from os.path import join

from .util import PoolObject, get_btc_price, form_traceback
from .constants import allowed_exchanges, trader_config, report_cols, trader_dumps, \
    trade_amount_per_thread, trade_time_period, exchanges_fees, max_tries_to_call_api, \
    pending_order_time, max_price_decrease, thread_cleaning_period

lock = RLock()


class Trader(PoolObject):
    def __init__(self):
        PoolObject.__init__(self)

        self.exchanges = {}
        self.threads = []
        self.free_balances = {}
        self.used_balances = {}
        self.locks = {}
        for ex in allowed_exchanges:
            self.locks[ex] = False

        self.meta = self.parse_xml()
        self.setup_clients()
        self.available = True

        print('trader: started')

    @staticmethod
    def parse_xml():
        tree = ElementTree.parse(trader_config)
        root = tree.getroot()
        meta = {}
        for key in root:
            meta[key[0].text] = {
                'public': key[1].text,
                'secret': key[2].text
            }
        return meta

    def setup_clients(self):
        self.exchanges['Bittrex'] = ccxt.bittrex({
            'apiKey': self.meta['Bittrex']['public'],
            'secret': self.meta['Bittrex']['secret'],
        })
        self.exchanges['Poloniex'] = ccxt.poloniex({
            'apiKey': self.meta['Poloniex']['public'],
            'secret': self.meta['Poloniex']['secret'],
        })
        self.exchanges['YoBit'] = ccxt.yobit({
            'apiKey': self.meta['YoBit']['public'],
            'secret': self.meta['YoBit']['secret'],
        })
        self.exchanges['HitBTC'] = ccxt.hitbtc2({
            'apiKey': self.meta['HitBTC']['public'],
            'secret': self.meta['HitBTC']['secret'],
        })
        self.exchanges['Tidex'] = ccxt.tidex({
            'apiKey': self.meta['Tidex']['public'],
            'secret': self.meta['Tidex']['secret'],
        })
        self.exchanges['Binance'] = ccxt.binance({
            'options': {'adjustForTimeDifference': True},
            'apiKey': self.meta['Binance']['public'],
            'secret': self.meta['Binance']['secret'],
        })
        self.exchanges['Bitfinex'] = ccxt.bitfinex({
            'apiKey': self.meta['Bitfinex']['public'],
            'secret': self.meta['Bitfinex']['secret'],
        })

    def fetch_balances(self):
        for exchange, client in self.exchanges.items():
            try:
                balances = client.fetch_balance()
                self.free_balances[exchange] = balances['free']
                self.used_balances[exchange] = balances['used']
                tickers_to_remove = []
                for ticker, quantity in self.free_balances[exchange].items():
                    if float(quantity) == 0 and ticker.lower() != 'btc':
                        tickers_to_remove.append(ticker)
                for ticker in tickers_to_remove:
                    self.free_balances[exchange].pop(ticker, None)
                tickers_to_remove = []

                for ticker, quantity in self.used_balances[exchange].items():
                    if float(quantity) == 0 and ticker.lower() != 'btc':
                        tickers_to_remove.append(ticker)
                for ticker in tickers_to_remove:
                    self.used_balances[exchange].pop(ticker, None)
            except Exception as exc:
                self.pool['bot'].send(['Something wrong happened during fetching ' + exchange + ' balance:', str(exc)])

    def get_report(self):
        self.fetch_balances()
        report = '    - Free balances:\n'
        for exchange, balance in self.free_balances.items():
            report += '        * {0}:\n'.format(exchange)
            for ticker, quantity in balance.items():
                price = get_btc_price()
                dollars = float(quantity) * price
                if ticker != 'BTC':
                    try:
                        ticker_price = self.exchanges[exchange].fetch_ticker(ticker + '/BTC')['last']
                    except Exception:
                        continue
                    dollars *= ticker_price
                if dollars < 0.01:
                    continue
                report += '            > {0}: {1:.8f} ({2:.2f}$)\n'.format(ticker, quantity, dollars)

        report += '    - Used balances:\n'
        for exchange, balance in self.used_balances.items():
            report += '        * {0}:\n'.format(exchange)
            for ticker, quantity in balance.items():
                price = get_btc_price()
                dollars = float(quantity) * price
                if ticker != 'BTC':
                    try:
                        ticker_price = self.exchanges[exchange].fetch_ticker(ticker + '/BTC')['last']
                    except Exception:
                        continue
                    dollars *= ticker_price
                if dollars < 0.01:
                    continue
                report += '            > {0}: {1:.8f} ({2:.2f}$)\n'.format(ticker, quantity, dollars)

        report += '    - Current trades:\n'
        for thread in self.threads:
            if not thread.is_alive():
                continue
            for k, v in thread.report.items():
                if k not in report_cols or v is None:
                    continue
                if k == 'signal_price' or ((k == 'buy_price' or k == 'sell_price') and v is not None):
                    report += '        * {0}: {1:.8f}\n'.format(k, v)
                else:
                    report += '        * {0}: {1}\n'.format(k, v)
            report += '\n'
        return report

    def make_trade(self, signal=None, report=None):
        if signal is None:
            exchange = report['exchange']
        else:
            exchange = signal['exchange']
        trader_thread = TraderThread(
            self,
            self.pool['bot'],
            self.pool['scribe'],
            self.exchanges[exchange],
            signal,
            report)
        trader_thread.setDaemon(True)
        trader_thread.start()
        self.threads.append(trader_thread)

    def restore_threads(self):
        if not os.path.exists(trader_dumps):
            os.makedirs(trader_dumps)
        dumps_filenames = os.listdir(trader_dumps)
        if len(dumps_filenames) == 0:
            return False
        for filename in dumps_filenames:
            with open(join(trader_dumps, filename), 'r') as file:
                report = json.load(file)
            self.make_trade(None, report)
        return True

    def dump_thread(self, report):
        if not os.path.exists(trader_dumps):
            os.makedirs(trader_dumps)
        try:
            filename = report['date'][:-9] + '_' + report['symbol'][:-4] + '_' + report['exchange']
            with open(join(trader_dumps, filename), 'w+') as file:
                json.dump(report, file)
        except Exception as exc:
            self.pool['bot'].send(['Something wrong happened during dumping thread:', str(exc)])

    def remove_thread_dump(self, report):
        try:
            filename = report['date'][:-9] + '_' + report['symbol'][:-4] + '_' + report['exchange']
            os.remove(join(trader_dumps, filename))
        except Exception as exc:
            self.pool['bot'].send(['Something wrong happened during removing the dump:', str(exc)])


class TraderThread(Thread):
    def __init__(self, trader, bot, scribe, client, signal=None, report=None):
        Thread.__init__(self)
        self.trader = trader
        self.bot = bot
        self.scribe = scribe
        self.client = client
        if report is None:
            self.report = {
                'id': signal['id'],
                'date': signal['date'],
                'symbol': signal['ticker'] + '/BTC',
                'exchange': signal['exchange'],
                'signal_price': signal['price_btc'],
                'bpi': signal['bpi'],
                'trade_amount_per_thread': trade_amount_per_thread,
                'time_to_trade_secs': trade_time_period,
                'estimated_profit': signal['estimated_profit'],
                'buy_price': None,
                'sell_price': None,
                'real_profit': None,
                'buy_order_id': None,
                'sell_order_id': None,
                'cancel_reason': None,
                'sell_reason': None,
                'work_time_secs': 0,
                'iteration_time_secs': client.rateLimit / 1000.0 + 0.1,
                'placed_buy_order': False,
                'bought': False,
                'placed_sell_order': False,
                'sold': False,
                'order_open_time': 0,
                'tries_to_call_api': 0
            }
        else:
            self.report = report

    def place_order(self, side, quantity, price):
        exception = None
        order = None
        while True:
            if self.report['tries_to_call_api'] > max_tries_to_call_api:
                self.bot.send(['Number of attempts to place {0} order exceeded: {1}'.format(side, str(exception))])
                self.report['tries_to_call_api'] = 0
                return
            try:
                time.sleep(self.report['iteration_time_secs'])
                self.report['work_time_secs'] += self.report['iteration_time_secs']
                order = self.client.create_order(
                    symbol=self.report['symbol'],
                    type='limit',
                    side=side,
                    amount=quantity,
                    price=price)
            except Exception as exc:
                exception = exc
                self.report['tries_to_call_api'] += 1
                continue
            self.report['tries_to_call_api'] = 0
            break
        if side == 'buy':
            self.report['buy_order_id'] = order['id']
            self.report['placed_buy_order'] = True
        else:
            self.report['sell_order_id'] = order['id']
            self.report['placed_sell_order'] = True

    def cancel_order(self, side):
        exception = None
        while True:
            if self.report['tries_to_call_api'] > max_tries_to_call_api:
                self.bot.send(['Number of attempts to cancel {0} order exceeded: {1}'.format(side, str(exception))])
                self.report['tries_to_call_api'] = 0
                return
            try:
                time.sleep(self.report['iteration_time_secs'])
                self.report['work_time_secs'] += self.report['iteration_time_secs']
                self.client.cancel_order(
                    self.report['buy_order_id'] if side == 'buy' else self.report['sell_order_id'],
                    self.report['symbol'])
            except Exception as exc:
                exception = exc
                self.report['tries_to_call_api'] += 1
                continue
            self.report['tries_to_call_api'] = 0
            break
        if side == 'buy':
            self.report['buy_order_id'] = None
            self.report['placed_buy_order'] = False
        else:
            self.report['sell_order_id'] = None
            self.report['placed_sell_order'] = False

    def fetch_order(self, side):
        exception = None
        while True:
            if self.report['tries_to_call_api'] > max_tries_to_call_api:
                self.bot.send(['Number of attempts to fetch {0} order info exceeded: {1}'.format(side, str(exception))])
                self.report['tries_to_call_api'] = 0
                return None
            try:
                time.sleep(self.report['iteration_time_secs'])
                self.report['work_time_secs'] += self.report['iteration_time_secs']
                self.report['order_open_time'] += self.report['iteration_time_secs']
                order_info = self.client.fetch_order(
                    self.report['buy_order_id'] if side == 'buy' else self.report['sell_order_id'],
                    self.report['symbol'])
            except Exception as exc:
                exception = exc
                self.report['tries_to_call_api'] += 1
                continue
            self.report['tries_to_call_api'] = 0
            return order_info

    def fetch_balance(self, category, ticker):
        exception = None
        while True:
            if self.report['tries_to_call_api'] > max_tries_to_call_api:
                self.bot.send(['Number of attempts to fetch {0} {1} balance exceeded: {2}'.format(
                    category,
                    ticker,
                    str(exception))])
                self.report['tries_to_call_api'] = 0
                return None
            try:
                time.sleep(self.report['iteration_time_secs'])
                self.report['work_time_secs'] += self.report['iteration_time_secs']
                balance = float(self.client.fetch_balance()[category][ticker])
            except Exception as exc:
                exception = exc
                self.report['tries_to_call_api'] += 1
                continue
            self.report['tries_to_call_api'] = 0
            return balance

    def fetch_token(self, when):
        exception = None
        while True:
            if self.report['tries_to_call_api'] > max_tries_to_call_api:
                self.bot.send(['Number of attempts to fetch ticker info ({0}) exceeded: {1}'.format(
                    when,
                    str(exception))])
                self.report['tries_to_call_api'] = 0
                return None
            try:
                time.sleep(self.report['iteration_time_secs'])
                self.report['work_time_secs'] += self.report['iteration_time_secs']
                ticker_stats = self.client.fetch_ticker(self.report['symbol'])
            except Exception as exc:
                exception = exc
                self.report['tries_to_call_api'] += 1
                continue
            self.report['tries_to_call_api'] = 0
            return ticker_stats

    def run(self):
        try:
            with lock:
                self.trader.locks[self.report['exchange']] = True

            while True:
                self.trader.dump_thread(self.report)

                if not self.report['placed_buy_order']:
                    btc_balance = self.fetch_balance('free', 'BTC')
                    if btc_balance is None:
                        self.report['cancel_reason'] = 'unable to fetch BTC balance before placing buy order'
                        break

                    needed_btc_balance = trade_amount_per_thread / float(self.report['bpi'])

                    ticker_stats = self.fetch_token('place buy')
                    if ticker_stats is None:
                        self.report['cancel_reason'] = 'unable to fetch token info before placing buy order'
                        break

                    last_price = ticker_stats['last']
                    pref_buy_price = ticker_stats['ask']
                    if btc_balance < needed_btc_balance:
                        needed_btc_balance = btc_balance
                    price_increase = (last_price / self.report['signal_price'] - 1) * 100
                    if price_increase > self.report['estimated_profit']:
                        self.report['cancel_reason'] = 'price increase is already higher than estimated profit'
                        break
                    self.report['estimated_profit'] -= price_increase

                    self.trader.dump_thread(self.report)

                    commission = exchanges_fees[self.report['exchange']] * needed_btc_balance
                    quantity_to_buy = self.client.amount_to_precision(
                        self.report['symbol'],
                        float((needed_btc_balance - commission) / pref_buy_price))
                    self.place_order('buy', quantity_to_buy, pref_buy_price)
                    if not self.report['placed_buy_order']:
                        self.report['cancel_reason'] = 'unable to place buy order'
                        break
                    self.trader.dump_thread(self.report)

                if self.report['placed_buy_order'] and not self.report['bought']:
                    order_info = self.fetch_order('buy')
                    if order_info is None:
                        self.report['cancel_reason'] = 'unable to fetch order info after placing buy order'
                        break

                    if self.report['order_open_time'] > pending_order_time:
                        self.report['order_open_time'] = 0
                        if order_info['status'] == 'open':
                            self.cancel_order('buy')
                            if self.report['placed_buy_order']:
                                self.report['cancel_reason'] = 'unable to cancel buy order'
                                break
                            continue
                        else:
                            self.report['bought'] = True
                            self.report['buy_price'] = order_info['price']
                            self.bot.send(['Trader:', 'Bought {0} on {1}'.format(self.report['symbol'],
                                                                                 self.report['exchange'])])
                    else:
                        if order_info['status'] == 'open':
                            continue
                        else:
                            self.report['bought'] = True
                            self.report['buy_price'] = order_info['price']
                            self.report['order_open_time'] = 0
                            self.bot.send(['Trader:', 'Bought {0} on {1}'.format(self.report['symbol'],
                                                                                 self.report['exchange'])])

                    self.trader.dump_thread(self.report)

                if self.report['bought'] and not self.report['placed_sell_order']:
                    ticker_stats = self.fetch_token('place sell')
                    if ticker_stats is None:
                        self.report['cancel_reason'] = 'unable to fetch token info before placing sell order'
                        break

                    pref_sell_price = ticker_stats['bid']
                    price_change = (pref_sell_price / self.report['buy_price'] - 1) * 100

                    if price_change < max_price_decrease:
                        self.report['sell_reason'] = 'price decreased more than on {0}%'.format(max_price_decrease)
                    elif price_change >= self.report['estimated_profit']:
                        self.report['sell_reason'] = 'price reached estimated value'
                    elif self.report['work_time_secs'] > trade_time_period:
                        self.report['sell_reason'] = 'trade time exceeded'
                    else:
                        continue

                    ticker_balance = self.fetch_balance('free', self.report['symbol'][:-4])
                    if ticker_balance is None:
                        self.report['cancel_reason'] = 'unable to to fetch token balance before placing sell order'
                        break

                    self.place_order('sell', ticker_balance, pref_sell_price)
                    if not self.report['placed_sell_order']:
                        self.report['cancel_reason'] = 'unable to place sell order'
                        break
                    self.trader.dump_thread(self.report)

                if self.report['placed_sell_order'] and not self.report['sold']:
                    order_info = self.fetch_order('sell')
                    if order_info is None:
                        self.report['cancel_reason'] = 'unable to fetch order info after placing sell order'
                        break

                    if self.report['order_open_time'] > pending_order_time:
                        self.report['order_open_time'] = 0
                        if order_info['status'] == 'open':
                            self.cancel_order('sell')
                            if self.report['placed_sell_order']:
                                self.report['cancel_reason'] = 'unable to cancel sell order'
                                break
                            continue
                        else:
                            self.report['sold'] = True
                            self.report['sell_price'] = order_info['price']
                            self.bot.send(['Trader:', 'Sold {0} on {1}'.format(self.report['symbol'],
                                                                               self.report['exchange'])])
                    else:
                        if order_info['status'] == 'open':
                            continue
                        else:
                            self.report['sold'] = True
                            self.report['sell_price'] = order_info['price']
                            self.report['order_open_time'] = 0
                            self.bot.send(['Trader:', 'Sold {0} on {1}'.format(self.report['symbol'],
                                                                               self.report['exchange'])])

                    self.trader.dump_thread(self.report)

                if self.report['sold']:
                    self.report['real_profit'] = (self.report['sell_price'] / self.report['buy_price'] - 1) * 100
                    break

            self.trader.dump_thread(self.report)

            with lock:
                self.trader.locks[self.report['exchange']] = False
                self.scribe.trade(self.report)
            self.trader.remove_thread_dump(self.report)
        except Exception as exc:
            self.bot.send(['Something wrong happened:', form_traceback(exc)])


class TraderThreadCleaner(Thread):
    def __init__(self, trader, bot):
        Thread.__init__(self)
        self.trader = trader
        self.bot = bot

    def run(self):
        while True:
            time.sleep(thread_cleaning_period)
            try:
                self.trader.threads = [t for t in self.trader.threads if t.is_alive()]
            except Exception as exc:
                self.bot.send(['Something wrong happened:', form_traceback(exc)])
