# engine/technical.py — 技術面計分（權重 25%）
import logging
import numpy as np
from db import query


def compute_technical_score(stock_id: str) -> float:
    try:
        df = query(f"""
            SELECT date, high, low, close, volume, turnover_rate
            FROM daily_price
            WHERE stock_id='{stock_id}'
            ORDER BY date DESC LIMIT 260
        """).sort_values("date")
    except Exception:
        return 50.0

    if len(df) < 60:
        return 50.0

    try:
        import talib
        HAS_TALIB = True
    except ImportError:
        HAS_TALIB = False

    c  = df["close"].values.astype(float)
    h  = df["high"].values.astype(float)
    lo = df["low"].values.astype(float)
    v  = df["volume"].values.astype(float)
    tr = df["turnover_rate"].values.astype(float)

    score = 0.0

    try:
        if HAS_TALIB:
            import talib
            # 均線多頭排列
            ma5   = talib.SMA(c, 5)[-1]
            ma20  = talib.SMA(c, 20)[-1]
            ma60  = talib.SMA(c, 60)[-1]
            ma120 = talib.SMA(c, 120)[-1] if len(c) >= 120 else ma60
            ma240 = talib.SMA(c, 240)[-1] if len(c) >= 240 else ma120

            if c[-1] > ma5 > ma20 > ma60 > ma120 > ma240:
                score += 20
            elif c[-1] < ma60:
                score -= 5

            # KD 指標
            k, d = talib.STOCH(h, lo, c, fastk_period=9)
            if k[-1] < 20 and k[-1] > d[-1]:
                score += 15
            elif k[-1] > 80 and k[-1] < d[-1]:
                score -= 10

            # MACD
            _, _, hist = talib.MACD(c)
            if len(hist) >= 2 and hist[-1] > 0 and hist[-2] < 0:
                score += 12

            # RSI
            rsi = talib.RSI(c, 14)[-1]
            if 50 <= rsi <= 70:
                score += 8
            elif rsi < 40:
                score -= 15

            # 布林通道
            upper, _, _ = talib.BBANDS(c)
            if c[-1] > upper[-1] and v[-1] > np.mean(v[-5:]) * 1.3:
                score += 10

        else:
            # TA-Lib 不可用時用純 numpy 簡化計算
            ma5  = np.mean(c[-5:])
            ma20 = np.mean(c[-20:])
            ma60 = np.mean(c[-60:])

            if c[-1] > ma5 > ma20 > ma60:
                score += 15
            elif c[-1] < ma60:
                score -= 5

            # 簡化 RSI
            diff  = np.diff(c[-15:])
            gains = diff[diff > 0].mean() if len(diff[diff > 0]) > 0 else 0
            loss  = -diff[diff < 0].mean() if len(diff[diff < 0]) > 0 else 1e-9
            rsi   = 100 - 100 / (1 + gains / loss)
            if 50 <= rsi <= 70:
                score += 8
            elif rsi < 40:
                score -= 10

        # 週轉率量增（不依賴 TA-Lib）
        if len(tr) >= 6 and np.mean(tr[-6:-1]) > 0:
            if tr[-1] > np.mean(tr[-6:-1]) * 1.5:
                score += 10

    except Exception as e:
        logging.warning(f"[technical] {stock_id} 計算失敗：{e}")
        return 50.0

    return max(0.0, min(100.0, score / 75.0 * 100))
