import csv
import re
import time
import requests

from xml.etree import ElementTree
from datetime import datetime
from threading import RLock

from .util import PoolObject, get_btc_price
from .constants import collector_config, allowed_exchanges, volume_threshold, predictor_dataset

lock = RLock()


class Collector(PoolObject):
    def __init__(self):
        PoolObject.__init__(self)

        self.meta = self.parse_xml()
        self.available = True

        print('collector: started')

    @staticmethod
    def parse_xml():
        tree = ElementTree.parse(collector_config)
        root = tree.getroot()
        meta = {
            'cryptoping_session': root[0].text,
            'cryptoping_session_name': root[1].text,
            'cryptoping_url': root[2].text,
            'dataset_size': int(root[3].text),
            'last_signal_id': int(root[4].text),
        }
        signal_exceptions = []
        for item in root[5]:
            signal_exceptions.append(item.text)
        meta['signal_exceptions'] = signal_exceptions
        return meta

    def update_xml(self):
        tree = ElementTree.parse(collector_config)
        root = tree.getroot()
        root[3].text = str(self.meta['dataset_size'])
        root[4].text = str(self.meta['last_signal_id'])
        tree.write(collector_config)

    def process_signal(self, msg):
        signal = Collector.parse_message(msg)
        signal['buy_vol_per'] = float(signal['buy_vol_per'])
        signal['buy_vol_btc'] = float(signal['buy_vol_btc'])
        signal['price_per'] = float(signal['price_per'])
        signal['price_btc'] = float(signal['price_btc'])
        signal['week_signals'] = int(signal['week_signals'])
        signal['cap'] = None if signal['cap'] == '' else float(signal['cap'])
        signal['1h_max'] = 0.0
        signal['6h_max'] = 0.0
        signal['24h_max'] = 0.0
        signal['48h_max'] = 0.0
        signal['7d_max'] = 0.0
        signal['bpi'] = get_btc_price()
        signal['volume'] = signal['buy_vol_btc'] / signal['buy_vol_per'] * 100 * 24

        waiting_time = 0
        while True:
            with lock:
                available = self.pool['predictor'].available
            if available:
                break
            time.sleep(1)
            waiting_time += 1
            if waiting_time >= 60:
                self.pool['bot'].send(['Collector:', 'Predictor is not available, waiting to process signal...'])
                waiting_time = 0

        pred = self.pool['predictor'].predict(signal)
        metrics = self.pool['predictor'].metrics
        signal['estimated_profit'] = pred
        ignore_reason = None

        if signal['exchange'] in allowed_exchanges:
            with lock:
                locked = self.pool['trader'].locks[signal['exchange']]
            if locked:
                ignore_reason = 'exchange balance locked'
            elif float(signal['volume']) * float(signal['bpi']) < volume_threshold:
                ignore_reason = 'low volume'
            elif pred < metrics['preds_75_percentile']:
                ignore_reason = 'low estimated profit'
        else:
            ignore_reason = 'not allowed exchange'

        if ignore_reason is None:
            self.pool['bot'].send([
                '[APPROVED]',
                '    - Ticker: ' + signal['ticker'],
                '    - Exchange: ' + signal['exchange'],
                '    - Signal price: {0:.8f}'.format(signal['price_btc']),
                '    - Estimated profit: ' + str(signal['estimated_profit'])])
            with lock:
                self.pool['scribe'].approved(signal)
            self.pool['trader'].make_trade(signal)
        else:
            signal['ignore_reason'] = ignore_reason
            self.pool['bot'].send([
                '[IGNORED]',
                '    - Ticker: ' + signal['ticker'],
                '    - Exchange: ' + signal['exchange'],
                '    - Signal price: {0:.8f}'.format(signal['price_btc']),
                '    - Estimated profit: ' + str(signal['estimated_profit']),
                '    - Ignore reason: ' + signal['ignore_reason']])
            with lock:
                self.pool['scribe'].ignored(signal)

    @staticmethod
    def parse_message(msg):
        message_tokens = re.split('\n|, ', msg.message)
        message = {
            'id': msg.id,
            'date': str(msg.date).split('+')[0],
            'ticker': message_tokens[0][3:],
            'exchange': message_tokens[1].split()[3],
            'buy_vol_per': message_tokens[2][1:-1],
            'buy_vol_btc': message_tokens[3].split()[4],
            'price_per': message_tokens[4][1:-1],
            'price_btc': message_tokens[5].split()[1],
            'week_signals': message_tokens[6].split()[1][:-3],
            'cap': message_tokens[7].split()[2][1:].replace(',', ''),
            '1h_max': '',
            '6h_max': '',
            '24h_max': '',
            '48h_max': '',
            '7d_max': '',
            'bpi': ''
        }
        return message

    @staticmethod
    def parse_page(resp):
        start_index = resp.find('<tbody>')
        end_index = resp.find('</tbody>')
        regexp = re.compile('<.*?>')
        signals_tokens = re.sub(regexp, ' ', resp[start_index:end_index]).split()
        signals_tokens = [st for st in signals_tokens if '/7d' not in st]
        parsed_signals = []
        i = 0
        while i < len(signals_tokens):
            signal = {
                'ticker': signals_tokens[i],
                'date': signals_tokens[i + 2] + ' ' + signals_tokens[i + 3],
                'price': signals_tokens[i + 4],
                '1h_max': signals_tokens[i + 5],
                '6h_max': signals_tokens[i + 7],
                '24h_max': signals_tokens[i + 9],
                '48h_max': signals_tokens[i + 11],
                '7d_max': signals_tokens[i + 13],
                'exchange': signals_tokens[i + 15]
            }
            parsed_signals.append(signal)
            i += 16
        return parsed_signals

    def update_dataset(self, new_items, rewrite=False):
        messages = []
        for item in new_items:
            parsed_message = self.parse_message(item)
            if str(parsed_message['date']) not in self.meta['signal_exceptions']:
                messages.append(self.parse_message(item))
        if len(messages) == 0:
            return
        columns = messages[0].keys()
        write_mode = 'w' if rewrite else 'a'
        with open(predictor_dataset, write_mode, newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            if rewrite:
                writer.writeheader()
            writer.writerows(messages)
        if rewrite:
            self.meta['dataset_size'] = len(messages)
        else:
            self.meta['dataset_size'] += len(messages)
        self.meta['last_signal_id'] = messages[-1]['id']
        self.update_xml()

    def complete_dataset(self):
        completed_samples = []
        samples_to_complete = []
        recent_samples = []
        now_utc = datetime.utcnow()
        with open(predictor_dataset, 'r', newline='') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row['7d_max'] != '':
                    completed_samples.append(row)
                else:
                    row_date = datetime.strptime(row['date'], '%Y-%m-%d %H:%M:%S')
                    if (now_utc - row_date).days >= 7:
                        samples_to_complete.append(row)
                    else:
                        recent_samples.append(row)
        samples_to_complete = list(reversed(samples_to_complete))

        if len(samples_to_complete) == 0:
            return

        page = 0
        i = 0
        not_completed = True
        while not_completed:
            page += 1
            cookie = {self.meta['cryptoping_session_name']: self.meta['cryptoping_session']}
            url = str(self.meta['cryptoping_url']) + str(page)
            resp = requests.get(url, cookies=cookie)
            parsed_signals = self.parse_page(resp.text)
            resp.close()
            j = 0

            prev_date = None
            cur_bpi = None

            while j < len(parsed_signals):
                row_date = datetime.strptime(samples_to_complete[i]['date'], '%Y-%m-%d %H:%M:%S')
                signal_date = datetime.strptime(parsed_signals[j]['date'], '%Y-%m-%d %H:%M')
                if row_date < signal_date:
                    signal_date, row_date = row_date, signal_date
                if samples_to_complete[i]['ticker'] == parsed_signals[j]['ticker'] and \
                   samples_to_complete[i]['price_btc'] == parsed_signals[j]['price'] and \
                   samples_to_complete[i]['exchange'].lower() == parsed_signals[j]['exchange'].lower() and \
                   (row_date - signal_date).seconds < 7200:
                    samples_to_complete[i]['1h_max'] = parsed_signals[j]['1h_max']
                    samples_to_complete[i]['6h_max'] = parsed_signals[j]['6h_max']
                    samples_to_complete[i]['24h_max'] = parsed_signals[j]['24h_max']
                    samples_to_complete[i]['48h_max'] = parsed_signals[j]['48h_max']
                    samples_to_complete[i]['7d_max'] = parsed_signals[j]['7d_max']

                    cur_date = str(samples_to_complete[i]['date'].split()[0])
                    if prev_date is None or cur_date != prev_date:
                        cur_bpi = get_btc_price(cur_date)
                        prev_date = cur_date
                        time.sleep(0.1)
                    samples_to_complete[i]['bpi'] = cur_bpi
                    # print('fulfilled at index', i, ': ', str(samples_to_complete[i]))
                    i += 1
                    if i == len(samples_to_complete):
                        not_completed = False
                        break
                else:
                    # print('stumbled at index ', i, ': ', str(samples_to_complete[i]))
                    pass
                j += 1
            time.sleep(1)
        columns = recent_samples[0].keys()
        with open(predictor_dataset, 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            writer.writerows(completed_samples)
            writer.writerows(reversed(samples_to_complete))
            writer.writerows(recent_samples)
