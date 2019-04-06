import csv
import os.path

from .util import PoolObject
from .constants import scribe_finished_trades, report_cols, scribe_ignored_signals, scribe_approved_signals


class Scribe(PoolObject):
    def __init__(self):
        PoolObject.__init__(self)

        self.available = True

        print('scribe: started')

    @staticmethod
    def get_report():
        count_of_signals = 3
        trade_signals = Scribe.read_from_csv(scribe_finished_trades, count_of_signals)
        report = '    - Last {0} trade signals\n'.format(count_of_signals)
        if len(trade_signals) == 0:
            report += '        * None\n'
            return report
        for signal in trade_signals:
            for k, v in signal.items():
                if k not in report_cols or v is None:
                    continue
                if str(v) != '':
                    if k == 'signal_price' or k == 'buy_price' or k == 'sell_price' or k == 'estimated_profit':
                        report += '        * {0}: {1:.8f}\n'.format(k, float(v))
                    else:
                        report += '        * {0}: {1}\n'.format(k, v)
            report += '\n'
        return report

    @staticmethod
    def ignored(signal):
        Scribe.write_to_csv(scribe_ignored_signals, signal)

    @staticmethod
    def approved(signal):
        Scribe.write_to_csv(scribe_approved_signals, signal)

    @staticmethod
    def trade(signal):
        Scribe.write_to_csv(scribe_finished_trades, signal)

    @staticmethod
    def write_to_csv(filename, signal):
        write_header = not os.path.isfile(filename)
        with open(filename, 'w' if write_header else 'a', newline='') as file:
            columns = signal.keys()
            writer = csv.DictWriter(file, fieldnames=columns)
            if write_header:
                writer.writeheader()
            writer.writerow(signal)

    @staticmethod
    def read_from_csv(filename, count_of_signals):
        signals = []
        if os.path.isfile(filename):
            with open(filename, 'r', newline='') as file:
                rows = list(csv.DictReader(file))[-count_of_signals:]
                for row in rows:
                    signals.append(row)
        return signals
