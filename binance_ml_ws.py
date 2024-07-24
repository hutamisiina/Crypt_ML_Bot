#必要なライブラリ読み込み
from apis import apis
import pybotters
import asyncio
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
from func import *

# 設定---------------------------------------------------------------------------------------------------------------------
symbols = ['GMTUSDT', 'APEUSDT']    # リストで設定。1つだけでも可能。['BTCUSDT','ETHUSDT']
exchange = 'Binance'    # モデルの読み込み時に使用。
interval = '15min'  # 1min, 3min, 5min, 15min, 30min, 1h, ,2h, 4h, 6h, 8h, 12h, 1D, 3D, 1w(20minや1M(一ヶ月)にはバイナンス側が対応してない)
interval_sec = 60*15    # 秒で指定。15分なら60*15。1日なら、60*60*24

# symbolごとのレバレッジ。1以下でも可能。というか１以上だとレバかけすぎ、ロジックがロジックなので突発的な値動きがあった際にはしっかり食らうから。石油王以外１以下推奨。最初にmain_pos_sizeとmax_pos_sizeが出ると思うのでそれを見ながら適当に調整。
# binance側でかならずこに記載したレバレッジ以上のレバレッジに設定しておく必要がある。
# 5ドル以下の注文は拒否されることある注意、これはバイナンス側の仕様。
leverage = {}
leverage[symbols[0]] = 0.5
leverage[symbols[1]] = 0.5

# 最大ポジション数。例えば新規の買いポジションを1とすると、次に売り決済と新規売りで2倍のポジションを取ることになるため、2を設定する。
# 変更しないで！変えるとどうなるか未検証
max_pos = 2

# symbolごとのポジションの細かさ
pos_pips = {}
pos_pips[symbols[0]] = 1
pos_pips[symbols[1]] = 1

# symbolごとのポジションの小数点以下の桁数(1→0, 0.1→1, 
pos_round_size = {}
pos_round_size[symbols[0]] = 0
pos_round_size[symbols[1]] = 0

# 証拠金として使う通貨(USDT, BUSD,...)
# 今どの通貨で資金を持っているか。先物ウォレットに入れておく
balance_asset = 'USDT'

# symbolごとの値段の細かさこれ書いた当時2021夏はBTC4万ドルとかだったのに今では7万ドル(2024年初夏）証拠金と現在のシンボルの価格に応じて
price_pips = {}
price_pips[symbols[0]] = 0.0001
price_pips[symbols[1]] = 0.001

# symbolごとの値段の小数点以下の桁数(1→0, 0.1→1, 0.01→2,
price_round_size = {}
price_round_size[symbols[0]] = 4
price_round_size[symbols[1]] = 3

# symbolごとの指値の距離(ATRにかける値)
# 変更する場合は、modelから作り直しになるので覚悟が必要
main_dist = {}
main_dist[symbols[0]] = 0.37
main_dist[symbols[1]] = 0.26

# symbolごとの指値の種類
# ATR, average, diff, squared, ATR_wma, ATR_each_sydeの三種類
# 他の指値にする場合は、modelから作り直す
limit_type = {}
limit_type[symbols[0]] = 'ATR_wma'
limit_type[symbols[1]] = 'ATR_wma'
rolling_period = 14 # 指値作成に使うperiodの設定

# 特徴量計算に使用するohlcvの長さ。
# 1000が最大。1001以上は不可。
# apiで各通貨1000取得して、ループ内でohlcv_lenの長さにカット。
ohlcv_len = 300

# 特徴量
# 絶対sortする。
features = {}
features[symbols[0]] = sorted([
    'hige_sita0',
    'hige_ue0',
    'ATR_per',
    'min_200',
    'max_200',
    'diff1',
    'NATR_per',
    'volume',
    'volume_per',
])
features[symbols[1]] = sorted([
    'hige_sita0',
    'hige_ue0',
    'ATR_per',
    'min_200',
    'max_200',
    'diff1',
    'NATR_per',
    'volume',
    'volume_per',
])
# 設定おわり---------------------------------------------------------------------------------------------------------------------

async def main():
    async with pybotters.Client(apis=apis, base_url="https://fapi.binance.com") as client:

        # pybottersのdatastoreを使用。
        store = pybotters.BinanceDataStore()

        # privateなstreamを受け取れるようにlistenKeyを取得しておく。(datastoreに格納されていつでも呼び出せる)
        await store.initialize(
            client.get('/fapi/v2/balance'),
            client.post('/fapi/v1/listenKey'),
        )
        for symbol in symbols:
            await store.initialize(
                client.get(f'/fapi/v2/positionRisk?symbol={symbol}'),
                client.get(f'/fapi/v1/openOrders?symbol={symbol}'),
            )


        streams = ''
        # symbolごとのpublicな値段(ticker)とか約定履歴(trades)とか
        for symbol in symbols:
            streams += '/'.join([
                f'{symbol.lower()}@aggTrade',
                f'{symbol.lower()}@ticker',
                f'{symbol.lower()}@kline_{interval.replace("in","").lower()}',
                #f'{symbol.lower()}_perpetual@continuousKline_1m',
            ])
            streams += '/'

        # 上でdatestoreに格納したlistenKeyを呼び出してstreamsの文字列に追加
        streams += '/'.join([store.listenkey])


        # streamsに色々追加したやつを使って、websocketに接続
        await client.ws_connect(
            f'wss://fstream.binance.com/stream?streams={streams}',
            hdlr_json=store.onmessage,
            heartbeat=10.0,
        )

        # wsに登録したものが、最初にある程度取得されるまで待つ。
        while not all([
            len(store.ticker) >= len(symbols),
            len(store.trade) > len(symbols)*5,
        ]):
            await store.wait()


        # balance_assetで設定した通貨が今どれくらいあるのかをapiを叩いて取得
        b_raw = await client.get('/fapi/v2/balance')
        all_balance = await b_raw.json()
        balance = choose_balance(all_balance, balance_asset)

        # 取得したbalanceからmain_pos_sizeを計算
        last_price = {}
        max_pos_size = {}
        main_pos_size = {}
        for symbol in symbols:

            last_price[symbol] = float(store.ticker.find({'s': symbol})[0]['c'])    # symbolごとの値段
            max_pos_size[symbol] = balance*leverage[symbol]/last_price[symbol]  # symbolごとの値段とレバレッジを使ってmax_pos_sizeを計算
            main_pos_size[symbol] = max_pos_size[symbol]/max_pos                # main_pos_sizeはmax_pos_sizeの1/2
            main_pos_size[symbol] = int(main_pos_size[symbol] * (10**pos_round_size[symbol]))/(10**pos_round_size[symbol])  # 上限を超えないように切り捨てる
            print('main_dist     :',main_dist[symbol])
            print('symbol        :',symbol)
            print(f'actualmargin :{balance:.2f}')
            print(f'max_pos_size :{max_pos_size[symbol]:.3f}')
            print(f'main_pos_size:{main_pos_size[symbol]:.3f}')
            print()

        # モデル読み込み
        model_y_buy, model_y_sell = {}, {}
        for symbol in symbols:
            model_y_buy[symbol], model_y_sell[symbol] = read_model(exchange, symbol, interval)


        # ohlcvを作る
        from_time = pd.to_datetime(datetime.now(timezone.utc)-timedelta(seconds=interval_sec*ohlcv_len+2))
        from_timestamp = datetime.timestamp(from_time)
        # 最初にohlcvを取得しておく。
        # 毎回取得していたら遅くなってしまうので、以降はtradesから最新のohlvを補間する形をとる。
        ohlcv = {}
        for symbol in symbols:
            params = {
                'symbol': symbol,
                'interval': interval.replace('in', ''),
                'startTime': int(from_timestamp*1000),
                'limit': 1000,
            }
            k_raw = await client.get('/fapi/v1/klines', params=params)
            data = await k_raw.json()
            
            ohlcv[symbol] = make_ohlcv(data)
            ohlcv[symbol] = ohlcv[symbol][ohlcv[symbol].index < datetime.now(timezone.utc)-timedelta(seconds=interval_sec)]


        prev_timestamp = interval_sec*int(datetime.timestamp(datetime.now(timezone.utc)) // interval_sec)
        ohlcv_ok = {}
        for symbol in symbols:
            ohlcv_ok[symbol] = False
        first = False

        # メインループ。ここまでは1度のみ行われる処理だが、以降はintervalごとにずっとループする。
        while True:

            await store.wait()
            st = datetime.now(timezone.utc)  # 処理の最後にed-stで処理時間を表示するためにスタート時間を記録しておく

            # intervalごとに処理を実行する。直前に処理を行った時間と異なっていれば実行するようになっている
            # くわしくはプログラムを読んでください。
            cur_timestamp = interval_sec*int(datetime.timestamp(st) // interval_sec)
            cur_time = pd.to_datetime(cur_timestamp, utc=True, unit='s')  # ジャストの時間を入れなおす。

            if prev_timestamp == cur_timestamp:
                continue
            elif prev_timestamp != cur_timestamp:
                
                first = True
                pass
            last_kline = {}

            for symbol in symbols:
                kline = pd.DataFrame(store.kline.find({'s': symbol}))
                cur_kline_time = pd.to_datetime(kline.at[kline.index[-1],'t'], unit='ms',utc=True)
                if cur_kline_time == cur_time:
                    ohlcv_ok[symbol]=True
            df = pd.DataFrame(store.kline.find())
            df.index = pd.to_datetime(df['t'],unit='ms',utc=True)

            if all(list(ohlcv_ok.values())) and first:
                first = False
                for symbol in symbols:
                    ohlcv_ok[symbol] = False
            else:
                continue
            prev_timestamp = cur_timestamp


            for symbol in symbols:
                raw_kline = store.kline.find({'s':symbol})
                last_kline[symbol] = make_last_kline(raw_kline, interval_sec, cur_time)
                #print(last_kline[symbol])
                ohlcv[symbol] = pd.concat([ohlcv[symbol], last_kline[symbol]], axis=0)

                # 長すぎる部分をカット
                if len(ohlcv[symbol]) > ohlcv_len+5:
                    ohlcv[symbol] = ohlcv[symbol].iloc[len(ohlcv[symbol])-(ohlcv_len+5):, :]

                ohlcv[symbol]['close'].fillna(method='ffill', inplace=True)
                ohlcv[symbol]['open'].fillna(value=ohlcv[symbol]['close'], inplace=True)
                ohlcv[symbol]['high'].fillna(value=ohlcv[symbol]['close'], inplace=True)
                ohlcv[symbol]['low'].fillna(value=ohlcv[symbol]['close'], inplace=True)
                #print(ohlcv[symbol])

            
            # 特徴量を計算する。
            df = {}
            for symbol in symbols:
                df[symbol] = calc_features(ohlcv[symbol], features[symbol])
                df[symbol].dropna(inplace=True)

            # ohlcvの最後の行から予測する。長くなったところはpredict関数にまとまっている
            pred_buy, pred_sell = {}, {}
            for symbol in symbols:
                pred_buy[symbol], pred_sell[symbol] = predict(df[symbol], features[symbol], model_y_buy[symbol], model_y_sell[symbol])


            # symbolごとの現在のポジションの大きさ(cur_pos_size)を取得する。
            cur_pos_size = {}
            for symbol in symbols:
                cur_pos_size[symbol] = float(store.position.find({'s': symbol})[0]['pa'])   # str型で取得されるのでfloatに変換


            # symbolごとに売買するポジション数の計算を行う。（実際の注文は最後）部分約定も考慮している。
            buy_pos_size, sell_pos_size = {}, {} # buy, sellでこれから売買するサイズ。決済分と新規注文分を足した分。
            
            for symbol in symbols:

                # buy, sellそれぞれに新規ポジ量と決済ポジ量を足していく形式で計算する。
                buy_pos_size[symbol] = 0.
                sell_pos_size[symbol] = 0.

                # 1. 現在のポジション(cur_pos_size)がないとき
                if cur_pos_size[symbol] == 0.:
                    if pred_buy[symbol] > 0.:   # richmanさんのチュートリアルに従って、pred_buyが0より大きければ新規買を行う。
                        buy_pos_size[symbol] += main_pos_size[symbol]
                    if pred_sell[symbol] > 0.:  # richmanさんのチュートリアルに従って、pred_sellが0より大きければ新規売を行う。
                        sell_pos_size[symbol] += main_pos_size[symbol]
                
                # 2. 現在買いのポジションを持っているとき
                elif cur_pos_size[symbol] > 0.:
                    # 買いポジションの決済
                    sell_pos_size[symbol] += cur_pos_size[symbol]

                    # 予測に従って新規買いポジションの計算を行う。
                    if pred_buy[symbol] > 0.:   # richmanさんのチュートリアルに従って、pred_buyが0より大きければ新規買を行う。
                        buy_pos_size[symbol] += np.minimum(main_pos_size[symbol] - cur_pos_size[symbol], main_pos_size[symbol]) # cur_pos_sizeは買っているなら+,売っているなら-なので、買いと売りで処理が若干異なる
                    if pred_sell[symbol] > 0.:  # richmanさんのチュートリアルに従って、pred_sellが0より大きければ新規売を行う。
                        sell_pos_size[symbol] += main_pos_size[symbol]

                # 3. 現在売りのポジションを持っているとき
                elif cur_pos_size[symbol] < 0.:
                    # 売りポジションの決済(買い)
                    buy_pos_size[symbol] += (-cur_pos_size[symbol])

                    # 予測に従って新規買いポジションの計算を行う。
                    if pred_buy[symbol] > 0.:  # richmanさんのチュートリアルに従って、pred_buyが0より大きければ新規買を行う。
                        buy_pos_size[symbol] += main_pos_size[symbol]
                    if pred_sell[symbol] > 0.:  # richmanさんのチュートリアルに従って、pred_sellが0より大きければ新規売を行う。
                        sell_pos_size[symbol] += np.minimum(main_pos_size[symbol] - (-cur_pos_size[symbol]), main_pos_size[symbol]) # cur_pos_sizeは買っているなら+,売っているなら-なので、買いと売りで処理が若干異なる
            
            # symbolごとにポジションのサイズを丸める
            limit_price_dist_ue, limit_price_dist_sita = {}, {} # 指値。ueとsitaで分かれているが、
            for symbol in symbols:
                buy_pos_size[symbol] = round(buy_pos_size[symbol], pos_round_size[symbol])
                sell_pos_size[symbol] = round(sell_pos_size[symbol], pos_round_size[symbol])


            # symbolごとに指値を丸める
            # ueとsitaで分けている。limit_typeによってはueとsitaの距離は同じになることもある。
            for symbol in symbols:
                limit_price_dist_ue[symbol], limit_price_dist_sita[symbol] = make_limit_price_dist(
                limit_type[symbol],
                main_dist[symbol],
                df[symbol],
                price_round_size[symbol],
                rolling_period=rolling_period
                )

            # symbols
            for symbol in symbols:
                # 指値価格を作成
                df[symbol]['buy_price'] = df[symbol]['close'] - limit_price_dist_sita[symbol]
                df[symbol]['sell_price'] = df[symbol]['close'] + limit_price_dist_ue[symbol]

                # 指値を丸める
                df[symbol]['buy_price'] = df[symbol]['buy_price'].round(price_round_size[symbol]).astype(float)
                df[symbol]['sell_price'] = df[symbol]['sell_price'].round(price_round_size[symbol]).astype(float)



            buy_price, sell_price = {}, {}
            for symbol in symbols:
                buy_price[symbol] = df[symbol]['buy_price'].values[-1]
                sell_price[symbol] = df[symbol]['sell_price'].values[-1]



            buy_flag, sell_flag = {}, {}

            # flagをFalseで新規作成。
            for symbol in symbols:
                buy_flag[symbol] = False
                sell_flag[symbol] = False



            # symbolごとに買いと売りのflagを立てていく
            for symbol in symbols:

                # 買い側のflag立て
                if buy_pos_size[symbol] == 0:
                    pass
                elif buy_pos_size[symbol] > 0.:
                    buy_flag[symbol] = True

                # 売り側のflag立て
                if sell_pos_size[symbol] == 0:
                    pass
                elif sell_pos_size[symbol] > 0.:
                    sell_flag[symbol] = True


            # キャンセルflagをFalseで作成
            all_del_flag = {}
            for symbol in symbols:
                all_del_flag[symbol] = False

            # symbolごとに刺さらなかった指値のキャンセルflagを立てていく
            for symbol in symbols:
                # 現在の注文状況
                orders_buy = store.order.find({'s': symbol, 'S': 'BUY'}) # buy側のdict型のオーダー情報がリストに入っている。[{},{},...]
                orders_sell = store.order.find({'s': symbol, 'S': 'SELL'})# sell側のdict型のオーダー情報がリストに入っている。[{},{},...]
                # 注文がない場合
                if len(orders_buy) == 0:
                    pass
                # 既に指値がある場合
                elif len(orders_buy) >= 1:
                    all_del_flag[symbol] = True


                # 注文がない場合
                if len(orders_sell) == 0:
                    pass
                # 既に指値がある場合
                elif len(orders_sell) >= 1:
                    all_del_flag[symbol] = True

                #print(orders_buy)
                #print(orders_sell)


            co_list = []
            del_co_list = []
            params_c, params_buy, params_sell = {}, {}, {}
            #print(all_del_flag)
            for symbol in symbols:

                # 全ての注文をキャンセル
                if all_del_flag[symbol]:
                    params_c[symbol] = {'symbol': symbol}
                    #print(params_c)
                    del_co_list.append(client.delete(f'/fapi/v1/allOpenOrders', data=params_c[symbol]))

            for symbol in symbols:
                # 指値注文
                if buy_flag[symbol]:
                    params_buy[symbol] = {
                        'symbol': symbol,
                        'side': 'BUY',
                        'type': 'LIMIT',
                        'quantity': round(buy_pos_size[symbol], pos_round_size[symbol]),
                        'price': buy_price[symbol],
                        'timeInForce': 'GTX',
                    }
                    co_list.append(client.post(f'/fapi/v1/order', data=params_buy[symbol]))

                if sell_flag[symbol]:
                    params_sell[symbol] = {
                        'symbol': symbol,
                        'side': 'SELL',
                        'type': 'LIMIT',
                        'quantity': round(sell_pos_size[symbol], pos_round_size[symbol]),
                        'price': sell_price[symbol],
                        'timeInForce': 'GTX',
                    }
                    co_list.append(client.post(f'/fapi/v1/order', data=params_sell[symbol]))

            
            print('注文数:', len(del_co_list)+len(co_list))
            ed = datetime.now(timezone.utc)

            # 注文キャンセル
            resp = await asyncio.gather(*del_co_list)
            for i in resp:
                data = await i.json()
                #print(data)

            # 新規注文
            resp = await asyncio.gather(*co_list)
            for i in resp:
                data = await i.json()
                #print(data)
        

            # 注文後に指値とかの情報を表示
            for symbol in symbols:
                if all_del_flag[symbol]:
                    print(f'{symbol}の全ての注文をキャンセル')

                if buy_flag[symbol]:
                    print(f'{symbol}の買い指値{buy_price[symbol]}({buy_pos_size[symbol]})')
                else:
                    print(f'{symbol}の買い指値{buy_price[symbol]}({buy_pos_size[symbol]})は入れませんでした。')
                if sell_flag[symbol]:
                    print(f'{symbol}の売り指値{sell_price[symbol]}({sell_pos_size[symbol]})')
                else:
                    print(f'{symbol}の売り指値{sell_price[symbol]}({sell_pos_size[symbol]})は入れませんでした。')

                print(f'pred_buy   :{pred_buy[symbol]:.6f}')
                print(f'pred_sell  :{pred_sell[symbol]:.6f}')
                print(f'pos_size   :{cur_pos_size[symbol]:.3f}')
                print()
            print('終了時間:',datetime.now(timezone.utc))
            print('計算にかかった時間:',f'{(ed-st).total_seconds():.3f}s')

            # balanceを取得
            res = await client.get('/fapi/v2/balance')
            all_balance = await res.json()
            balance = choose_balance(all_balance, balance_asset)

            # balaceからsymbolごとのmain_pos_sizeを再計算
            for symbol in symbols:
                max_pos_size[symbol] = balance*leverage[symbol]/float(store.ticker.find({'s': symbol})[0]['c'])
                main_pos_size[symbol] = max_pos_size[symbol]/max_pos
                main_pos_size[symbol] = int(main_pos_size[symbol] * (10**pos_round_size[symbol]))/(10**pos_round_size[symbol])  # 上限を超えないように切り捨てる

            print()


if __name__ == '__main__':

    try:
       asyncio.run(main())

    except KeyboardInterrupt:
       pass
