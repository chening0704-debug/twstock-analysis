# engine/technical.py — 技術面計分（pandas-ta 版本）
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
        import pandas_ta as ta

        c  = df["close"].astype(float)
        h  = df["high"].astype(float)
        lo = df["low"].astype(float)
        v  = df["volume"].astype(float)
        tr = df["turnover_rate"].astype(float)

        score = 0.0

        # 均線多頭排列
        ma5   = ta.sma(c, length=5).iloc[-1]
        ma20  = ta.sma(c, length=20).iloc[-1]
        ma60  = ta.sma(c, length=60).iloc[-1]
        ma120 = ta.sma(c, length=120).iloc[-1] if len(c) >= 120 else ma60
        ma240 = ta.sma(c, length=240).iloc[-1] if len(c) >= 240 else ma120
        cur   = float(c.iloc[-1])

        if cur > ma5 > ma20 > ma60 > ma120 > ma240:
            score += 20
        elif cur < ma60:
            score -= 5

        # KD 指標（Stochastic）
        stoch = ta.stoch(h, lo, c, k=9, d=3)
        if stoch is not None and not stoch.empty:
            k_col = [col for col in stoch.columns if 'STOCHk' in col]
            d_col = [col for col in stoch.columns if 'STOCHd' in col]
            if k_col and d_col:
                k_val = float(stoch[k_col[0]].iloc[-1])
                d_val = float(stoch[d_col[0]].iloc[-1])
                if k_val < 20 and k_val > d_val:
                    score += 15
                elif k_val > 80 and k_val < d_val:
                    score -= 10

        # MACD
        macd_df = ta.macd(c)
        if macd_df is not None and not macd_df.empty:
            hist_col = [col for col in macd_df.columns if 'MACDh' in col]
            if hist_col:
                hist = macd_df[hist_col[0]]
                if len(hist) >= 2:
                    if float(hist.iloc[-1]) > 0 and float(hist.iloc[-2]) < 0:
                        score += 12

        # RSI
        rsi_series = ta.rsi(c, length=14)
        if rsi_series is not None and not rsi_series.empty:
            rsi = float(rsi_series.iloc[-1])
            if 50 <= rsi <= 70:
                score += 8
            elif rsi < 40:
                score -= 15

        # 布林通道
        bbands = ta.bbands(c, length=20)
        if bbands is not None and not bbands.empty:
            upper_col = [col for col in bbands.columns if 'BBU' in col]
            if upper_col:
                upper = float(bbands[upper_col[0]].iloc[-1])
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
