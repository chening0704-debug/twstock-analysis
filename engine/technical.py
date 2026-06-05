# engine/technical.py — 技術面計分 v2
# 修正：降低最低資料需求，確保短期也能計算
import logging
import numpy as np
import pandas as pd
from db import query


def _ema(data: np.ndarray, period: int) -> np.ndarray:
    k   = 2.0 / (period + 1)
    out = np.zeros(len(data))
    out[0] = data[0]
    for i in range(1, len(data)):
        out[i] = data[i] * k + out[i-1] * (1-k)
    return out


def _sma(data: np.ndarray, period: int) -> float:
    if len(data) < period:
        return float(np.mean(data))
    return float(np.mean(data[-period:]))


def _rsi(closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    diff  = np.diff(closes[-(period+2):])
    gains = diff[diff > 0]
    loss  = -diff[diff < 0]
    avg_g = float(np.mean(gains)) if len(gains) > 0 else 0.001
    avg_l = float(np.mean(loss))  if len(loss)  > 0 else 0.001
    rs    = avg_g / (avg_l + 1e-9)
    return 100 - 100 / (1 + rs)


def compute_technical_score(stock_id: str) -> float:
    try:
        df = query(f"""
            SELECT date, high, low, close, volume, turnover_rate
            FROM daily_price
            WHERE stock_id = '{stock_id}'
            AND volume > 0
            ORDER BY date DESC LIMIT 260
        """).sort_values("date").reset_index(drop=True)
    except Exception as e:
        logging.warning(f"[technical] {stock_id} 查詢失敗：{e}")
        return 50.0

    n = len(df)

    # 資料不足 5 日直接回傳中性
    if n < 5:
        return 50.0

    c  = df["close"].values.astype(float)
    h  = df["high"].values.astype(float)
    lo = df["low"].values.astype(float)
    v  = df["volume"].values.astype(float)
    tr = df["turnover_rate"].values.astype(float)

    score = 0.0
    cur   = c[-1]

    try:
        # ── 均線評分（動態調整期數）──────────────────────────
        ma5  = _sma(c, min(5,  n))
        ma20 = _sma(c, min(20, n))
        ma60 = _sma(c, min(60, n))

        if n >= 60:
            ma120 = _sma(c, min(120, n))
            if cur > ma5 > ma20 > ma60 > ma120:
                score += 25   # 完整多頭排列
            elif cur > ma5 > ma20 > ma60:
                score += 18
            elif cur > ma20:
                score += 8
            elif cur < ma60:
                score -= 8
        elif n >= 20:
            if cur > ma5 > ma20:
                score += 18
            elif cur > ma20:
                score += 8
            elif cur < ma20:
                score -= 5
        else:
            if cur > ma5:
                score += 10
            else:
                score -= 3

        # ── MACD（最少需要 26 日）────────────────────────────
        if n >= 26:
            ema12 = _ema(c, 12)
            ema26 = _ema(c, 26)
            dif   = ema12 - ema26
            sig   = _ema(dif, 9)
            hist  = dif - sig

            if len(hist) >= 2:
                if hist[-1] > 0 and hist[-2] < 0:
                    score += 15   # 金叉
                elif hist[-1] > 0 and hist[-1] > hist[-2]:
                    score += 10   # 正值擴大
                elif hist[-1] > 0:
                    score += 5    # 正值區
                elif hist[-1] < 0 and hist[-2] > 0:
                    score -= 10   # 死叉
                elif hist[-1] < hist[-2] < 0:
                    score -= 5    # 負值擴大

        # ── RSI ────────────────────────────────────────────
        if n >= 15:
            rsi = _rsi(c, 14)
            if 50 <= rsi <= 70:
                score += 10
            elif rsi > 80:
                score -= 5    # 過熱
            elif 35 <= rsi < 50:
                score += 3
            elif rsi < 30:
                score += 8    # 超賣反彈

        # ── KD（Stochastic，最少 9 日）──────────────────────
        if n >= 10:
            period_k = min(9, n-1)
            low_k    = np.array([np.min(lo[max(0,i-period_k):i+1])
                                 for i in range(len(c))])
            high_k   = np.array([np.max(h[max(0,i-period_k):i+1])
                                 for i in range(len(c))])
            rsv  = (c - low_k) / (high_k - low_k + 1e-9) * 100
            K    = _ema(rsv, 3)
            D    = _ema(K,   3)
            k_v  = K[-1]
            d_v  = D[-1]

            if k_v < 20 and k_v > d_v:
                score += 15   # 超賣黃金交叉
            elif k_v < 30 and k_v > d_v:
                score += 8
            elif k_v > 80 and k_v < d_v:
                score -= 10   # 超買死叉
            elif 50 < k_v < 80 and k_v > d_v:
                score += 5

        # ── 量能評分 ─────────────────────────────────────────
        if n >= 6:
            avg_v5 = np.mean(v[-6:-1])
            v_ratio= v[-1] / (avg_v5 + 1e-9)
            day_chg= (c[-1] - c[-2]) / (c[-2] + 1e-9) * 100 \
                     if n >= 2 else 0

            if v_ratio >= 3.0 and day_chg > 2:
                score += 15   # 大爆量上攻
            elif v_ratio >= 2.0 and day_chg > 1:
                score += 10
            elif v_ratio >= 1.5 and day_chg > 0:
                score += 5
            elif v_ratio >= 2.0 and day_chg < -2:
                score -= 8    # 大量下跌

        # ── 週轉率 ───────────────────────────────────────────
        if n >= 6 and np.mean(tr[-6:-1]) > 0:
            tr_ratio = tr[-1] / (np.mean(tr[-6:-1]) + 1e-9)
            if tr_ratio >= 2.0:
                score += 8
            elif tr_ratio >= 1.5:
                score += 4

        # ── 布林通道（需20日）────────────────────────────────
        if n >= 20:
            ma20_arr = np.array([
                np.mean(c[max(0,i-19):i+1])
                for i in range(len(c))
            ])
            std20 = np.array([
                np.std(c[max(0,i-19):i+1])
                for i in range(len(c))
            ])
            upper = ma20_arr + 2 * std20
            lower = ma20_arr - 2 * std20

            bb_pos = (c[-1] - lower[-1]) / (upper[-1] - lower[-1] + 1e-9)
            if bb_pos > 1.0 and v[-1] > np.mean(v[-6:]) * 1.5:
                score += 10   # 突破上軌帶量
            elif bb_pos > 0.8:
                score += 5
            elif bb_pos < 0.1:
                score += 5    # 觸及下軌反彈機會

    except Exception as e:
        logging.warning(f"[technical] {stock_id} 計算失敗：{e}")
        return 50.0

    final = max(0.0, min(100.0, score))
    logging.debug(
        f"[technical] {stock_id} n={n} 分數={final:.1f}"
    )
    return final
