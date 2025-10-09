# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
import glob

class BigInteger(fields.Integer):
    column_type = ('int8', 'int8')

fields.BigInteger = BigInteger


class TradeAggs(models.AbstractModel):
    _name = "trade.aggs"
    _description = "Trade Aggs"

    ticker = fields.Char()
    volume = fields.Float()
    open = fields.Float()
    close = fields.Float()
    high = fields.Float()
    low = fields.Float()
    window_start = fields.BigInteger()
    transactions = fields.BigInteger()

    def _import_aggs(self, path):
        fnames = glob.glob(f'{path}/*.csv.gz')
        fnames.sort()
        for i, fname in enumerate(fnames):
            if i % 100 == 0:
                print(f"{i} / {len(fnames)}")
            self.env.cr.execute(f"COPY {self._table}(ticker,volume,open,close,high,low,window_start,transactions) FROM PROGRAM 'gzip -dc {fname}' DELIMITER ',' CSV HEADER NULL ''")



class DayAggs(models.Model):
    _name = "min.aggs"
    _inherit = ['trade.aggs']
    _description = "Min Aggs"

    def cron_import(self):
        self._import_aggs('/home/elmeri/Work/polygon/us_stocks_sip/minute_aggs_v1/*/*')

    # ticker,volume,open,close,high,low,window_start,transactions
    # A,115,89.53,89.53,89.53,89.53,1594033200000000000,2
    # A,101,89.8,89.8,89.8,89.8,1594037220000000000,2
    # A,100,89.01,89.01,89.01,89.01,1594038480000000000,1
    # A,40541,89.02,89.43,89.43,89.02,1594042200000000000,


class DayAggs(models.Model):
    _name = "day.aggs"
    _inherit = ['trade.aggs']
    _description = "Day Aggs"
    # COPY day_aggs(ticker,volume,open,close,high,low,window_start,transactions) FROM PROGRAM 'gzip -dc /home/elmeri/Work/polygon/2020-07-06.csv.gz' DELIMITER ',' CSV HEADER NULL '';


    def cron_import(self):
        self._import_aggs('/home/elmeri/Work/polygon/us_stocks_sip/day_aggs_v1/*/*')


    # ticker,volume,open,close,high,low,window_start,transactions
    # A,1409981,89.02,89.31,90.64,89.02,1594008000000000000,15449
    # AA,7084253,11.35,11.47,11.5748,11.02,1594008000000000000,34347

    def cron_analyze(self):
        import pandas as pd
        import glob
        import pickle
        import os
        from collections import defaultdict
        from dateutil.relativedelta import relativedelta


        CHANGE_UP = 1.00 # 100%
        MAX_HODL = 1 # days
        FADE_DOWN = -0.05 # 5%
        FADE_WINDOW = 30 # 30mins
        STOP_LOSS = 1.00 # 100%
        TAKE_PROFIT = -0.1 # 10% below 10d_ma
        MIN_PRICE = 0.15
        COST = 5


        # https://polygon.io/blog/hunting-anomalies-in-the-stock-market

        # df = pd.read_csv('us_stocks_sip/day_aggs_v1/2020/07/2020-07-06.csv.gz', compression='gzip')

        dfs_pickle_fname = 'dfs.pkl'

        if os.path.isfile(dfs_pickle_fname):
            print(" Cached dfs..", end="\r")
            with open(dfs_pickle_fname, 'rb') as f:
                dfs = pickle.load(f)
        else:
            print(" Fresh dfs..", end="\r")
            dfs = {}
            fnames = glob.glob('us_stocks_sip/day_tickers/*.csv.gz')
            fnames.sort()
            for fname in fnames:
                ticker = os.path.basename(fname).split('.csv.gz')[0]
                df = pd.read_csv(fname, compression='gzip')
                dfs[ticker] = df
                df['time'] = pd.to_datetime(df["window_start"], unit="ns")
                df.set_index('time')
                df['10d_ma'] = df['close'].rolling(window=10).mean()

            with open(dfs_pickle_fname, 'wb') as f:
                pickle.dump(dfs, f)


        anoms_pickle_fname = 'anoms.pkl'
        if os.path.isfile(anoms_pickle_fname):
            print(" Cached anoms..", end="\r")
            with open(anoms_pickle_fname, 'rb') as f:
                anoms = pickle.load(f)
        else:
            print(" Fresh anoms..", end="\r")
            anoms = {}
            for ticker, df in dfs.items():
                if not ticker.endswith('.WS'):
                    df['prev_close'] = df['close'].shift(1)
                    df['open_change'] = ((df['open'] - df['prev_close']) / df['prev_close'])
                    df['high_change'] = ((df['high'] - df['prev_close']) / df['prev_close'])
                    anoms[ticker] = df[(df['high_change'] >= CHANGE_UP) | df['open_change'] >= CHANGE_UP]

            with open(anoms_pickle_fname, 'wb') as f:
                pickle.dump(anoms, f)

        # TODO
        # etsi osakkeet jotka avasi +100% edellisestä sulku hinnasta, ja katso kuinka usein close hinta on pienempi kuin open.
        print("Anomalies found", len(anoms))


        ptic = defaultdict(list)

        wins = 0
        losses = 0
        plist = []
        wl_ratio = 0
        average = 0
        count = 0
        for ticker, days in anoms.items():
            if len(ticker) > 4 and not any(ticker.endswith(e) for e in ['A', 'B']):
                # https://www.nasdaqtrader.com/content/technicalsupport/specifications/dataproducts/nasdaqfifthcharactersuffixlist.pdf
                continue # TODO better way to exclude warrants...

            fname = f'us_stocks_sip/minute_tickers/{ticker}.csv.gz'
            if not os.path.isfile(fname):
                # print("Missing ", fname)
                continue

            count += 1
            mins = pd.read_csv(fname, compression='gzip')
            mins['time'] = pd.to_datetime(mins["window_start"], unit="ns")
            mins.set_index('time')
            mins['fade'] = mins['close'].rolling(window=FADE_WINDOW).mean()


            for idx, drow in days.iterrows():
                prev = drow['prev_close']
                top = drow['open']
                if top <= MIN_PRICE:
                    continue
                d10_ma = drow['10d_ma']
                high = drow['high']

                intraday = mins[(mins['time'] >= drow['time']) & (mins['time'] <= drow['time'] + relativedelta(days=MAX_HODL))]
                if len(intraday) > 0:
                    sell = False
                    buy = False
                    profit = False

                    for idx, tick in intraday.iterrows():
                        price = tick['close']
                        fade = tick['fade']
                        time = tick['time']
                        top = max(top, price)
                        trend_diff = (price - d10_ma)/d10_ma
                        top_diff = (fade - top) / top
                        prev_diff = (price - prev) / prev

                        if not sell and trend_diff >= CHANGE_UP and prev_diff >= CHANGE_UP and top_diff <= FADE_DOWN:
                            sell = price
                            continue

                        if sell and price > sell*(1+STOP_LOSS):
                            buy = price
                            profit = (sell - buy)/sell
                            print("SL", ticker, time,  f"{prev=:.2f}", f"{high=:.2f}", f"{sell=:.2f}", f"{buy=:.2f}", f"{profit*100=:.2f}", f"{average=:.2f}, {wl_ratio=:.2f}", sep='\t')
                            break

                        if sell and trend_diff <= TAKE_PROFIT:
                            buy = price
                            profit = (sell - buy)/sell
                            print("TP", ticker, time,  f"{prev=:.2f}", f"{high=:.2f}", f"{sell=:.2f}", f"{buy=:.2f}", f"{profit*100=:.2f}", f"{average=:.2f}, {wl_ratio=:.2f}", sep='\t')
                            break

                    else:
                        if sell:
                            buy = price
                            profit = (sell - buy)/sell
                            print("Time", ticker, time,  f"{prev=:.2f}", f"{high=:.2f}", f"{sell=:.2f}", f"{buy=:.2f}", f"{profit*100=:.2f}", f"{average=:.2f}, {wl_ratio=:.2f}", sep='\t')

                    if profit is not False:
                        if profit > 0:
                            wins += 1
                        else:
                            losses += 1

                        plist.append(profit)
                        ptic[ticker].append({
                            'profit': profit,
                            'time': time,
                            'prev': prev,
                            'high': high,
                            'sell': sell,
                            'buy': buy,
                            'intraday': intraday,
                        })
                        wl_ratio = wins / losses if losses else 0
                        average = sum(plist) / len(plist) if plist else 0



            if count >= 100:
                break

        ptic_pickle_fname = 'ptic.pkl'
        with open(ptic_pickle_fname, 'wb') as f:
            pickle.dump(ptic, f)


        # print(ptic)
        wl_ratio = wins / losses
        average = sum(plist) / len(plist)
        print(f"{average=}, {wl_ratio=}")









