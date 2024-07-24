# Crypt_ML_Bot

This is a set that can be used all the way through to backtesting and actual operation of richmanbtc's(https://github.com/richmanbtc/mlbot_tutorial?tab=readme-ov-file) MLbot.

 
 A detailed explanation is commented in the code, but I will explain it lightly here as well.The language used is python.It has been tested on windows 10, but has not been tested on other environments.

Overview
　This set includes everything from downloading execution data from Binance, creating OHLCV, backtesting richmanbtc's MLbot, to actual operation. Original limit price and features are also included.

Program to download execution data and create ohlcv(func.py)
　It supports all USDⓈ-M currency pairs on Binance.

Program for backtesting(back_test.py)
　Can be used for any currency pair on any exchange, not just Binance, as long as the format of the ohlcv is matched.

Operational bot(binance_ml_ws.py)
　It supports all USDⓈ-M currency pairs on Binance. By default, the parameters are the same as in the backtest image below, and can be run by simply setting the API key.
Original limit price (8 limits except volume)
Original features (5 except default ATR)


Binanceでの約定データのダウンロード、OHLCVの作成（ローソク足をバイナンスのAPI叩いて作ります）、richmanbtcさんのMLbotチュートリアル（https://github.com/richmanbtc/mlbot_tutorial?tab=readme-ov-file) を雛形として特徴量の生成とバックテストから実稼働まで一通りできるシステム群になります。細かいことはコードに日本語コメント書いてありますのでここでは botの挙動の流れを軽く説明します。


binance_ml_ws.py：メインロジック。後述のapis.pyにバイナンスのAPIを入力してws.pyを実行すると動きます。
func.py:binance_ml_ws.pyで使う関数をまとめたやつ、後述のback_tesu_use.pyで作った機械学習モデルの読み込みとかをここでやります。
apis.py:バイナンスのAPI叩くやつ口座開設するとプライベートAPI発行できます。
back_test.py,backtest_func.py,backtest_use/py:バックテストを実行します。メインを動かすと自動で動きます。
