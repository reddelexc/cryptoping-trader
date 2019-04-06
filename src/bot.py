from telegram.ext import Updater, CommandHandler
from xml.etree import ElementTree

from .util import PoolObject, form_traceback, get_btc_price
from .constants import proxy_host, proxy_port, tg_bot_config


class Bot(PoolObject):
    def __init__(self, proxy=False):
        PoolObject.__init__(self)

        self.meta = self.parse_xml()
        if proxy:
            self.updater = Updater(
                self.meta['bot_token'],
                request_kwargs={'proxy_url': 'socks5://{0}:{1}'.format(proxy_host, proxy_port)}
            )
        else:
            self.updater = Updater(self.meta['bot_token'])
        self.dispatcher = self.updater.dispatcher
        self.add_handlers()
        self.updater.start_polling()
        self.available = True

        print('bot: started')

    @staticmethod
    def parse_xml():
        tree = ElementTree.parse(tg_bot_config)
        root = tree.getroot()
        meta = {
            'owner_id': root[0].text,
            'bot_token': root[1].text
        }
        return meta

    def auth(self, chat_id):
        return str(chat_id) == self.meta['owner_id']

    def send(self, tokens):
        try:
            tokens = [str(token) for token in tokens]
            self.updater.bot.send_message(self.meta['owner_id'], '\n'.join(tokens))
        except Exception as exc:
            print('failed to send message: {0}, through bot: {1}'.format(tokens, exc))
            self.updater.bot.send_message(self.meta['owner_id'], '\n'.join(tokens))

    def add_handlers(self):
        self.dispatcher.add_handler(CommandHandler('say_hi', self.say_hi))
        self.dispatcher.add_handler(CommandHandler('get_predictor_report', self.get_predictor_report))
        self.dispatcher.add_handler(CommandHandler('get_scribe_report', self.get_scribe_report))
        self.dispatcher.add_handler(CommandHandler('get_trader_report', self.get_trader_report))
        self.dispatcher.add_handler(CommandHandler('start_listener', self.start_listener))
        self.dispatcher.add_handler(CommandHandler('stop_listener', self.stop_listener))
        self.dispatcher.add_handler(CommandHandler('cur_listener_status', self.cur_listener_status))
        self.dispatcher.add_handler(CommandHandler('update_dataset', self.update_dataset))
        self.dispatcher.add_handler(CommandHandler('rewrite_dataset', self.rewrite_dataset))
        self.dispatcher.add_handler(CommandHandler('complete_dataset', self.complete_dataset))
        self.dispatcher.add_handler(CommandHandler('cur_dataset_size', self.cur_dataset_size))
        self.dispatcher.add_handler(CommandHandler('cur_btc_price', self.cur_btc_price))
        self.dispatcher.add_handler(CommandHandler('restore_threads', self.restore_threads))

    def say_hi(self, _, update):
        if not self.auth(update.message.chat_id):
            return
        update.message.reply_text('hi')

    def get_predictor_report(self, _, update):
        if not self.auth(update.message.chat_id):
            return
        try:
            update.message.reply_text('Predictor:\n' + self.pool['predictor'].get_report())
        except Exception as exc:
            update.message.reply_text('Something wrong happened:\n' + form_traceback(exc))

    def get_scribe_report(self, _, update):
        if not self.auth(update.message.chat_id):
            return
        try:
            update.message.reply_text('Scribe:\n' + self.pool['scribe'].get_report())
        except Exception as exc:
            update.message.reply_text('Something wrong happened:\n' + form_traceback(exc))

    def get_trader_report(self, _, update):
        if not self.auth(update.message.chat_id):
            return
        try:
            update.message.reply_text('Trader:\n' + self.pool['trader'].get_report())
        except Exception as exc:
            update.message.reply_text('Something wrong happened:\n' + form_traceback(exc))

    def start_listener(self, _, update):
        if not self.auth(update.message.chat_id):
            return
        try:
            self.pool['client'].start_listener()
            update.message.reply_text('Started listener')
        except Exception as exc:
            update.message.reply_text('Something wrong happened:\n' + form_traceback(exc))

    def stop_listener(self, _, update):
        if not self.auth(update.message.chat_id):
            return
        try:
            self.pool['client'].stop_listener()
            update.message.reply_text('Stopped listener')
        except Exception as exc:
            update.message.reply_text('Something wrong happened:\n' + form_traceback(exc))

    def cur_listener_status(self, _, update):
        if not self.auth(update.message.chat_id):
            return
        try:
            if self.pool['client'].cur_listener_status():
                update.message.reply_text('Listener is active')
            else:
                update.message.reply_text('Listener is inactive')
        except Exception as exc:
            update.message.reply_text('Something wrong happened:\n' + form_traceback(exc))

    def update_dataset(self, _, update):
        if not self.auth(update.message.chat_id):
            return
        update.message.reply_text('Updating dataset...')
        try:
            self.pool['client'].update_dataset()
            update.message.reply_text('Dataset updated')
        except Exception as exc:
            update.message.reply_text('Something wrong happened:\n' + form_traceback(exc))

    def rewrite_dataset(self, _, update):
        if not self.auth(update.message.chat_id):
            return
        update.message.reply_text('Rewriting dataset...')
        try:
            self.pool['client'].rewrite_dataset()
            update.message.reply_text('Dataset rewritten')
        except Exception as exc:
            update.message.reply_text('Something wrong happened:\n' + form_traceback(exc))

    def complete_dataset(self, _, update):
        if not self.auth(update.message.chat_id):
            return
        update.message.reply_text('Completing dataset...')
        try:
            self.pool['client'].complete_dataset()
            update.message.reply_text('Dataset completed')
        except Exception as exc:
            update.message.reply_text('Something wrong happened:\n' + form_traceback(exc))

    def cur_dataset_size(self, _, update):
        if not self.auth(update.message.chat_id):
            return
        try:
            size = self.pool['client'].cur_dataset_size()
            update.message.reply_text('Dataset size is ' + str(size))
        except Exception as exc:
            update.message.reply_text('Something wrong happened:\n' + form_traceback(exc))

    def cur_btc_price(self, _, update):
        if not self.auth(update.message.chat_id):
            return
        try:
            price = get_btc_price()
            update.message.reply_text('Current Bitcoin price is {0:.0f}$'.format(price))
        except Exception as exc:
            update.message.reply_text('Something wrong happened:\n' + form_traceback(exc))

    def restore_threads(self, _, update):
        if not self.auth(update.message.chat_id):
            return
        try:
            result = self.pool['trader'].restore_threads()
            if result:
                update.message.reply_text('Trader threads restored')
            else:
                update.message.reply_text('Not trader threads to restore')

        except Exception as exc:
            update.message.reply_text('Something wrong happened:\n' + form_traceback(exc))
