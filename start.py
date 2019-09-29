import sys

from src import Bot, Client, Collector, \
    Predictor, PredictorLearnThread, Scribe, \
    Trader, TraderThreadCleaner, GarbageCleanerThread

if __name__ == '__main__':
    with_proxy = len(sys.argv) > 1 and sys.argv[1] == '-p'
    pool = {
        'client': Client(with_proxy),
        'bot': Bot(with_proxy),
        'collector': Collector(),
        'predictor': Predictor(),
        'scribe': Scribe(),
        'trader': Trader(),
    }

    for _, entity in pool.items():
        entity.set_pool(pool)

    garbage_cleaning_thread = GarbageCleanerThread(pool['bot'])
    garbage_cleaning_thread.setDaemon(True)
    garbage_cleaning_thread.start()

    predictor_learn_thread = PredictorLearnThread(pool['predictor'], pool['client'], pool['bot'])
    predictor_learn_thread.setDaemon(True)
    predictor_learn_thread.start()

    trader_thread_cleaner = TraderThreadCleaner(pool['trader'], pool['bot'])
    trader_thread_cleaner.setDaemon(True)
    trader_thread_cleaner.start()
