import socks
import os

from xml.etree import ElementTree
from telethon import TelegramClient, events, utils
from telethon.errors import SessionPasswordNeededError

from .util import PoolObject, form_traceback
from .constants import data, client_tg_session, proxy_host, proxy_port, tg_client_config


class Client(TelegramClient, PoolObject):
    def __init__(self, proxy=False):
        PoolObject.__init__(self)

        self.meta = self.parse_xml()
        self.listener_status = False
        if not os.path.exists(data):
            os.makedirs(data)
        if proxy:
            super().__init__(
                client_tg_session,
                self.meta['api_id'],
                self.meta['api_hash'],
                proxy=(socks.SOCKS5, proxy_host, proxy_port),
            )
        else:
            super().__init__(
                client_tg_session,
                self.meta['api_id'],
                self.meta['api_hash'],
            )
        try:
            self.connect()
        except ConnectionError:
            print('client: 1st connect failed, 2nd connect...')
            self.connect()

        if not self.is_user_authorized():
            print('client: sending code to authorize...')
            self.sign_in(self.meta['owner_phone'])
            self_user = None
            while self_user is None:
                code = input('client: enter the code: ')
                try:
                    self_user = self.sign_in(code=code)
                except SessionPasswordNeededError:
                    pw = input('client: enter 2fa pass: ')
                    self_user = self.sign_in(password=pw)
        self.available = True
        print('client: started')

    @staticmethod
    def parse_xml():
        tree = ElementTree.parse(tg_client_config)
        root = tree.getroot()
        meta = {
            'owner_phone': root[0].text,
            'api_id': root[1].text,
            'api_hash': root[2].text,
            'cryptoping_bot_id': root[3].text
        }
        return meta

    def update_handler(self, update):
        update = update.original_update
        if str(update.user_id) == self.meta['cryptoping_bot_id'] and update.message.startswith('💎'):
            try:
                self.pool['collector'].process_signal(update)
            except Exception as exc:
                self.pool['bot'].send(['Something wrong happened:', form_traceback(exc)])

    def start_listener(self):
        if self.listener_status:
            return
        self.listener_status = True
        self.add_event_handler(self.update_handler, events.NewMessage)

    def stop_listener(self):
        if not self.listener_status:
            return
        self.listener_status = False
        self.remove_event_handler(self.update_handler, events.NewMessage)

    def cur_listener_status(self):
        return self.listener_status

    def get_cryptoping_entity(self):
        dialogs = self.get_dialogs()
        for dialog in dialogs:
            if utils.get_display_name(dialog.entity) == 'CryptoPing':
                return dialog.entity
        return None

    def update_dataset(self):
        cryptoping_dialog_entity = self.get_cryptoping_entity()
        messages = []
        for msg in reversed(self.get_messages(
                cryptoping_dialog_entity,
                limit=None,
                min_id=self.pool['collector'].meta['last_signal_id'])):
            if msg.message.startswith('💎'):
                messages.append(msg)
        self.pool['collector'].update_dataset(messages)

    def rewrite_dataset(self):
        cryptoping_dialog_entity = self.get_cryptoping_entity()
        messages = []
        for msg in reversed(self.get_messages(cryptoping_dialog_entity, limit=None)):
            if msg.message.startswith('💎'):
                messages.append(msg)
        self.pool['collector'].update_dataset(messages, rewrite=True)

    def complete_dataset(self):
        self.pool['collector'].complete_dataset()

    def cur_dataset_size(self):
        return self.pool['collector'].meta['dataset_size']
