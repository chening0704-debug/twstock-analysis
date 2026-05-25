# engine/technical.py — 技術面計分（ta 套件版本，相容 Python 3.11）
import logging
import numpy as np
import pandas as pd
from db import query


def compute_technical_score(stock_id: str) -> float:
    try:
        df = query(f"""
            SELECT date, high, low, close, volume, turnover_rate
            FROM daily_price
            WHERE stock_id='{stock_id}'
            ORDER BY date DESC LIMIT 260
        """).sort_values("date").reset_index(drop=True)
    except Exception:
        return 50.0

    if len(df) < 60:
        return 50.0

    try:
        import ta
        from ta.trend import SMAIndicator, MACD
        from ta.momentum import StochasticOscillator, RSIIndicator
        from ta.volatility import BollingerBands

        c  = df["close"].astype(float)
        h  = df["high"].astype(float)
        lo = df["low"].astype(float)
        v  = df["volume"].astype(float)
        tr = df["turnover_rate"].astype(float)

        score = 0.0
        cur   = float(c.iloc[-1])

        # 均線多頭排列
        ma5   = float(SMAIndicator(c, window=5).sma_indicator().iloc[-1])
        ma20  = float(SMAIndicator(c, window=20).sma_indicator().iloc[-1])
        ma60  = float(SMAIndicator(c, window=60).sma_indicator().iloc[-1])
        ma120 = float(SMAIndicator(c, window=min(120, len(c))).sma_indicator().iloc[-1])
        ma240 = float(SMAIndicator(c, window=min(240, len(c))).sma_indicator().iloc[-1])

        if cur > ma5 > ma20 > ma60 > ma120 > ma240:
            score += 20
        elif cur < ma60:
            score -= 5

        # KD 指標
        stoch = StochasticOscillator(
            high=h, low=lo, close=c, window=9, smooth_window=3
        )
        k_val = float(stoch.stoch().iloc[-1])
        d_val = float(stoch.stoch_signal().iloc[-1])
        if k_val < 20 and k_val > d_val:
            score += 15
        elif k_val > 80 and k_val < d_val:
            score -= 10

        # MACD
        macd_ind  = MACD(close=c)
        hist_now  = float(macd_ind.macd_diff().iloc[-1])
        hist_prev = float(macd_ind.macd_diff().iloc[-2])
        if hist_now > 0 and hist_prev < 0:
            score += 12

        # RSI
        rsi = float(RSIIndicator(close=c, window=14).rsi().iloc[-1])
        if 50 <= rsi <= 70:
            score += 8
        elif rsi < 40:
            score -= 15

        # 布林通道
        bb    = BollingerBands(close=c, window=20)
        upper = float(bb.bollinger_hband().iloc[-1])
        v_arr = v.values
        if cur > upper and v_arr[-1] > np.mean(v_arr[-5:]) * 1.3:
            score += 10

        # 週轉率量增
        tr_arr = tr.values
        if len(tr_arr) >= 6 and np.mean(tr_arr[-6:-1]) > 0:
            if tr_arr[-1] > np.mean(tr_arr[-6:-1]) * 1.5:
                score += 10

    except Exception as e:
        logging.warning(f"[technical] {stock_id} 計算失敗：{e}")
        return 50.0

    return max(0.0, min(100.0, score / 75.0 * 100))
