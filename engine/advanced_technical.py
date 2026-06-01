# engine/advanced_technical.py
# 進階技術指標模組
# 新增：BIAS乖離率、PSY心理線、量價關係
#       K棒型態識別、三線合一噴發偵測
#       大師鐵律多指標一致性評分

import numpy as np
import pandas as pd
import logging
from db import query


def compute_bias(closes: np.ndarray) -> dict:
    """
    BIAS 乖離率計算
    BIAS = (收盤價 - N日均線) / N日均線 × 100
    """
    result = {}
    for n, key in [(5,"bias5"), (10,"bias10"), (20,"bias20")]:
        if len(closes) >= n:
            ma  = np.mean(closes[-n:])
            val = (closes[-1] - ma) / (ma + 1e-9) * 100
            result[key] = round(float(val), 2)
        else:
            result[key] = 0.0
    return result


def compute_psy(closes: np.ndarray, period: int = 12) -> float:
    """
    PSY 心理線
    PSY = 上漲天數 / 統計天數 × 100
    正常區間 25~75，> 75 過熱，< 25 超賣
    """
    if len(closes) < period + 1:
        return 50.0
    diffs     = np.diff(closes[-(period+1):])
    up_days   = (diffs > 0).sum()
    psy       = up_days / period * 100
    return round(float(psy), 2)


def compute_volume_price_score(
    prices: pd.DataFrame,
    volumes: np.ndarray
) -> tuple:
    """
    量價關係評分（最高 25 分）
    量增價漲：主力進場訊號
    量縮價漲：短線過熱注意
    量增價跌：主力出貨警示
    量縮價跌：賣壓減輕
    """
    score  = 0.0
    detail = {}
    c      = prices["close"].values.astype(float)
    v      = volumes.astype(float)

    if len(c) < 6 or len(v) < 6:
        return 0.0, {}

    # 今日量比（今日量 / 5日均量）
    avg_vol_5  = np.mean(v[-6:-1])
    vol_ratio  = v[-1] / (avg_vol_5 + 1e-9)

    # 今日漲跌
    day_chg    = (c[-1] - c[-2]) / (c[-2] + 1e-9) * 100

    # 近5日量能趨勢
    vol_trend  = (np.mean(v[-3:]) - np.mean(v[-6:-3])) / (np.mean(v[-6:-3]) + 1e-9) * 100

    detail["量比"]    = f"{vol_ratio:.2f}倍"
    detail["今日漲跌"] = f"{day_chg:+.2f}%"
    detail["量能趨勢"] = f"{vol_trend:+.1f}%"

    # 量增價漲（最強訊號）
    if vol_ratio >= 2.0 and day_chg > 2.0:
        score += 20
        detail["量價形態"] = "量增價漲★★★ (+20)"
    elif vol_ratio >= 1.5 and day_chg > 1.0:
        score += 15
        detail["量價形態"] = "量增價漲★★ (+15)"
    elif vol_ratio >= 1.2 and day_chg > 0:
        score += 10
        detail["量價形態"] = "量增價漲★ (+10)"

    # 量縮價漲（短線注意）
    elif vol_ratio < 0.8 and day_chg > 1.0:
        score += 5
        detail["量價形態"] = "量縮價漲（短線注意）(+5)"

    # 量增價跌（主力出貨警示）
    elif vol_ratio >= 1.5 and day_chg < -1.0:
        score -= 10
        detail["量價形態"] = "量增價跌⚠️ 主力出貨？(-10)"

    # 量縮價跌（賣壓減輕）
    elif vol_ratio < 0.8 and day_chg < -1.0:
        score += 3
        detail["量價形態"] = "量縮價跌（賣壓減輕）(+3)"

    # 量能趨勢加分（近3日量能持續放大）
    if vol_trend > 20 and day_chg > 0:
        score += 5
        detail["量能加成"] = "近3日量能持續放大 (+5)"

    return min(max(score, -15), 25), detail


def detect_candle_pattern(prices: pd.DataFrame) -> dict:
    """
    K棒型態識別
    識別：一字漲停、長紅K突破、T字底、十字星
    """
    result = {}
    if len(prices) < 3:
        return result

    o = float(prices["open"].iloc[-1])
    h = float(prices["high"].iloc[-1])
    l = float(prices["low"].iloc[-1])
    c = float(prices["close"].iloc[-1])

    body      = abs(c - o)
    amplitude = h - l
    body_ratio= body / (amplitude + 1e-9)
    chg_pct   = (c - float(prices["close"].iloc[-2])) / (float(prices["close"].iloc[-2]) + 1e-9) * 100

    # 一字漲停（開盤即漲停）
    if chg_pct >= 9.5 and body_ratio > 0.9:
        result["pattern"] = "一字漲停"
        result["pattern_score"] = 15
        result["pattern_desc"]  = "主力強勢鎖單，籌碼高度集中"

    # 長紅K突破（實體 > 振幅60%，漲幅 > 3%）
    elif chg_pct >= 3.0 and body_ratio >= 0.6 and c > o:
        result["pattern"] = "長紅K突破"
        result["pattern_score"] = 10
        result["pattern_desc"]  = "多方主導，買盤積極，有效突破"

    # 帶量紅K（普通紅K）
    elif chg_pct >= 1.0 and c > o:
        result["pattern"] = "紅K"
        result["pattern_score"] = 5
        result["pattern_desc"]  = "多方佔優"

    # T字底（開低收高，下影線長）
    elif (c - l) / (amplitude + 1e-9) > 0.7 and chg_pct > 0:
        result["pattern"] = "T字底"
        result["pattern_score"] = 8
        result["pattern_desc"]  = "低點支撐強勁，買盤承接積極"

    # 十字星（猶豫訊號）
    elif body_ratio < 0.1:
        result["pattern"] = "十字星"
        result["pattern_score"] = 0
        result["pattern_desc"]  = "多空拉鋸，等待方向確認"

    # 長黑K（空方主導）
    elif chg_pct <= -3.0 and body_ratio >= 0.6 and c < o:
        result["pattern"] = "長黑K"
        result["pattern_score"] = -10
        result["pattern_desc"]  = "空方主導，賣壓沉重"

    else:
        result["pattern"] = "普通K棒"
        result["pattern_score"] = 0
        result["pattern_desc"]  = ""

    return result


def detect_triple_line_breakout(closes: np.ndarray) -> dict:
    """
    三線合一噴發偵測
    5MA / 10MA / 20MA 同時上穿 → 強力起漲訊號
    """
    result = {"triple_breakout": False, "score": 0, "desc": ""}

    if len(closes) < 22:
        return result

    c     = closes.astype(float)
    ma5   = np.mean(c[-5:])
    ma10  = np.mean(c[-10:])
    ma20  = np.mean(c[-20:])

    # 昨日均線
    ma5_prev  = np.mean(c[-6:-1])
    ma10_prev = np.mean(c[-11:-1])
    ma20_prev = np.mean(c[-21:-1])

    cur = c[-1]

    # 三線合一：三條均線緊密聚合
    spread = (max(ma5, ma10, ma20) - min(ma5, ma10, ma20)) / min(ma5, ma10, ma20) * 100

    # 今日同時站上三條均線
    above_all_now  = cur > ma5 and cur > ma10 and cur > ma20
    above_all_prev = c[-2] > ma5_prev and c[-2] > ma10_prev and c[-2] > ma20_prev

    # 昨日任一在均線下方，今日全部突破
    was_below_any = (c[-2] < ma5_prev or c[-2] < ma10_prev or c[-2] < ma20_prev)

    if above_all_now and was_below_any and spread < 5.0:
        result["triple_breakout"] = True
        result["score"]  = 20
        result["spread"] = round(spread, 2)
        result["desc"]   = f"三線合一噴發！三線價差{spread:.1f}% → 強力起漲訊號 (+20)"
    elif above_all_now and spread < 3.0:
        result["triple_breakout"] = True
        result["score"]  = 12
        result["spread"] = round(spread, 2)
        result["desc"]   = f"三線糾結突破（價差{spread:.1f}%）(+12)"
    elif above_all_now:
        result["score"] = 5
        result["desc"]  = "站上三條均線上方 (+5)"

    return result


def compute_master_rule_score(
    stock_id: str,
    prices:   pd.DataFrame,
    volumes:  np.ndarray,
) -> dict:
    """
    大師鐵律一致性評分
    技術面、量價面、籌碼面三者同向時給予加分
    任一出現背離時給予警示

    評分項目：
    1. 紀律與趨勢（順勢操作）
    2. 均線檢核（股價 > 20MA）
    3. K線訊號
    4. 量價關係
    5. MACD 指標
    6. 心理線 PSY
    """
    result  = {}
    total   = 0.0
    c       = prices["close"].values.astype(float)
    v       = volumes.astype(float)

    if len(c) < 22:
        return {"master_score": 0.0, "details": {}}

    # 1. 均線檢核（股價 > 20MA 為必要條件）
    ma20 = np.mean(c[-20:])
    ma5  = np.mean(c[-5:])
    if c[-1] > ma20:
        total += 15
        result["均線檢核"] = f"股價{c[-1]:.1f} > 20MA{ma20:.1f} ✅ (+15)"
    else:
        total -= 10
        result["均線檢核"] = f"股價{c[-1]:.1f} < 20MA{ma20:.1f} ❌ (-10)"

    # 2. 紀律與趨勢（近20日漲幅 > 0 且均線多頭）
    chg_20 = (c[-1] - c[-21]) / (c[-21] + 1e-9) * 100 if len(c) >= 21 else 0
    if chg_20 > 5 and c[-1] > ma5 > ma20:
        total += 15
        result["紀律趨勢"] = f"多頭趨勢確認，20日漲{chg_20:.1f}% (+15)"
    elif chg_20 > 0:
        total += 8
        result["紀律趨勢"] = f"趨勢向上，20日漲{chg_20:.1f}% (+8)"
    else:
        result["紀律趨勢"] = f"趨勢偏弱，20日漲跌{chg_20:.1f}% (0)"

    # 3. MACD 檢核
    def ema(data, n):
        k   = 2.0/(n+1)
        out = np.zeros(len(data))
        out[0] = data[0]
        for i in range(1, len(data)):
            out[i] = data[i]*k + out[i-1]*(1-k)
        return out

    ema12 = ema(c, 12)
    ema26 = ema(c, 26)
    dif   = ema12 - ema26
    sig   = ema(dif, 9)
    hist  = dif - sig

    if hist[-1] > 0 and hist[-2] < 0:
        total += 20
        result["MACD指標"] = f"OSC={hist[-1]:.4f}翻正，金叉意圖明確 (+20)"
    elif hist[-1] > 0 and hist[-1] > hist[-2]:
        total += 12
        result["MACD指標"] = f"OSC={hist[-1]:.4f}正值且增大 (+12)"
    elif hist[-1] > 0:
        total += 8
        result["MACD指標"] = f"OSC={hist[-1]:.4f}正值區 (+8)"
    else:
        result["MACD指標"] = f"OSC={hist[-1]:.4f}負值區 (0)"

    # 4. 心理線 PSY
    psy = compute_psy(c, 12)
    if 40 <= psy <= 65:
        total += 15
        result["心理線PSY"] = f"PSY={psy:.0f}，健康上升區 (+15)"
    elif psy > 75:
        total -= 5
        result["心理線PSY"] = f"PSY={psy:.0f}，過熱警示 (-5)"
    elif psy < 25:
        total += 10
        result["心理線PSY"] = f"PSY={psy:.0f}，超賣反彈機會 (+10)"
    else:
        total += 5
        result["心理線PSY"] = f"PSY={psy:.0f} (+5)"

    # 5. 量價一致性
    _, vp_detail = compute_volume_price_score(prices, v)
    vp_form = vp_detail.get("量價形態", "")
    if "量增價漲★★★" in vp_form:
        total += 20
        result["量價關係"] = f"底部價量齊揚 → 初升段價量齊揚 (+20)"
    elif "量增價漲" in vp_form:
        total += 12
        result["量價關係"] = "量價同向 (+12)"
    elif "出貨" in vp_form:
        total -= 10
        result["量價關係"] = "量增價跌，警示 (-10)"
    else:
        result["量價關係"] = "量價中性 (0)"

    # 6. BIAS 乖離率
    bias = compute_bias(c)
    b5   = bias.get("bias5", 0)
    b20  = bias.get("bias20", 0)
    if 0 < b5 <= 8 and b20 > 0:
        total += 15
        result["BIAS乖離"] = f"BIAS5={b5:.1f}% BIAS20={b20:.1f}%，位置適中 (+15)"
    elif b5 > 12:
        total -= 5
        result["BIAS乖離"] = f"BIAS5={b5:.1f}%偏高，短線過熱 (-5)"
    elif b5 < -5:
        total += 8
        result["BIAS乖離"] = f"BIAS5={b5:.1f}%，超跌反彈機會 (+8)"
    else:
        result["BIAS乖離"] = f"BIAS5={b5:.1f}% (+0)"

    return {
        "master_score": round(min(max(total, 0), 100), 1),
        "details":      result,
        "bias":         bias,
        "psy":          psy,
    }


def compute_advanced_score(stock_id: str) -> dict:
    """
    計算進階技術分析完整評分
    整合所有新增指標
    """
    try:
        prices = query(f"""
            SELECT date, open, high, low, close, volume
            FROM daily_price
            WHERE stock_id = '{stock_id}'
            AND volume > 0
            ORDER BY date DESC LIMIT 130
        """).sort_values("date").reset_index(drop=True)

        if len(prices) < 22:
            return {"advanced_score": 0.0, "details": {}}

        volumes = prices["volume"].values.astype(float)
        closes  = prices["close"].values.astype(float)

        # 各子模組計算
        bias           = compute_bias(closes)
        psy            = compute_psy(closes, 12)
        vp_score, vp_d = compute_volume_price_score(prices, volumes)
        candle         = detect_candle_pattern(prices)
        triple         = detect_triple_line_breakout(closes)
        master         = compute_master_rule_score(
            stock_id, prices, volumes
        )

        # 綜合進階評分
        adv_score = (
            master["master_score"] * 0.5
            + max(vp_score, 0) * 0.3
            + candle.get("pattern_score", 0) * 0.1
            + triple.get("score", 0) * 0.1
        )
        adv_score = min(max(adv_score, 0), 100)

        return {
            "advanced_score":     round(adv_score, 1),
            "master_score":       master["master_score"],
            "master_details":     master["details"],
            "bias":               bias,
            "psy":                round(psy, 1),
            "volume_price_score": round(vp_score, 1),
            "volume_price_detail":vp_d,
            "candle_pattern":     candle,
            "triple_breakout":    triple,
        }

    except Exception as e:
        logging.warning(f"[AdvancedTech] {stock_id} 失敗：{e}")
        return {"advanced_score": 0.0, "details": {}}
