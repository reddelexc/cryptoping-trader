Trading system for altcoins which is able to:

- Collect signals from [CryptoPing](https://cryptoping.tech) Telegram bot
- Match signals from this bot to signals from [CryptoPing](https://cryptoping.tech) site
- Learn to predict expected signal profit (RandomForest)
- Listen for incoming signals in Telegram
- Buy altcoins which have good predictions on 8 crypto exchanges: Bittrex, Poloniex, YoBit, Cryptopia, HitBTC, Tidex, Binance, Bitfinex
- Give reports about prediction model performance, exchanges balances, current trades and finished trades in separate Telegram bot

Every setting that can be tuned placed in `/src/constants.py`. All api keys, session tokens, and other sensitive values can be filled in configs placed in `/configs`.

Full dataset collected starting from August 2017 can be found on [Kaggle](https://www.kaggle.com/reddelexc/crypto-assets-signals/activity), feel free to experiment with it.