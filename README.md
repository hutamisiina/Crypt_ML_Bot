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
