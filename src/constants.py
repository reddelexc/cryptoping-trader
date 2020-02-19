proxy_host = '127.0.0.1'
proxy_port = 1080

collector_config = 'configs/collector.xml'
trader_config = 'configs/trader.xml'
tg_bot_config = 'configs/tg_bot.xml'
tg_client_config = 'configs/tg_client.xml'

data = 'data/'
client_tg_session = 'data/tg_client'
predictor_dataset = 'data/dataset.csv'
scribe_ignored_signals = 'data/scribe_ignored.csv'
scribe_approved_signals = 'data/scribe_approved.csv'
scribe_finished_trades = 'data/scribe_trades.csv'
trained_model = 'data/trained_model/'
trader_dumps = 'data/trader_dumps/'

predictor_target_col = '24h_per'

predictor_main_cols = [
    'ticker',
    'exchange',
    'buy_vol_per',
    'buy_vol_btc',
    'price_per',
    'week_signals',
    'hour',
    'bpi',
    '24h_per'
]

predictor_dummy_cols = [
    'ticker',
    'exchange'
]

allowed_exchanges = [
    'Poloniex'
    # 'Bittrex',
    'YoBit',
    'HitBTC',
    'Binance',
    'Bitfinex'
    # 'Tidex'
]

necessary_exchange_methods = [
    'cancelOrder',
    'createOrder',
    'createLimitOrder',
    'editOrder',
    'fetchBalance',
    'fetchClosedOrders',
    'fetchL2OrderBook',
    'fetchOpenOrders',
    'fetchOrder',
    'fetchTicker',
    'fetchTrades',
    'withdraw'
]

report_cols = [
    'date',
    'symbol',
    'exchange',
    'signal_price',
    'bpi',
    'trade_amount_per_thread',
    'time_to_trade_secs',
    'estimated_profit',
    'real_profit',
    'buy_price',
    'sell_price',
    'cancel_reason',
    'sell_reason'
]

# in percent
exchanges_fees = {
    'YoBit': 0.002,
    'Cryptopia': 0.002,
    'Bittrex': 0.0025,
    'HitBTC': 0.002,
    'Binance': 0.001
}

# dollars
volume_threshold = 2000
trade_amount_per_thread = 10

# percent
max_price_decrease = -5

# seconds
learning_period = 86400
thread_cleaning_period = 43200
trade_time_period = 86400
garbage_cleaning_period = 10800
pending_order_time = 20
max_tries_to_call_api = 10
