# engine/flying_stock.py
# 飆股基因分析引擎
# 圖片來源：飆股基因 5大特徵 + 4階段最強飆股模型
# 完整融入台股智能分析系統

import logging
import numpy as np
import pandas as pd
from db import query


# ══════════════════════════════════════════════════════════════
# 評分門檻定義
# ══════════════════════════════════════════════════════════════
FLYING_SCORE_STRONG  = 75   # 強力飆股訊號
FLYING_SCORE_FORMING = 60   # 條件成形中
FLYING_SCORE_WATCH   = 45   # 持續追蹤
# < 45 → 飆股基因不足


# ══════════════════════════════════════════════════════════════
# 特徵一：長時間橫盤整理（最高 20 分）
# ══════════════════════════════════════════════════════════════
def _score_consolidation(
    prices: pd.DataFrame,
    volumes: np.ndarray
) -> tuple[float, dict]:
    """
    評估股票是否有足夠的橫盤整理：
    1. 低量橫盤 20 日以上           → +10 分
    2. 均線糾結（5/20/60 三線 < 3%）→ +5 分
    3. 近 20 日振幅 < 10%           → +5 分
    """
    score  = 0.0
    detail = {}
    c      = prices["close"].values.astype(float)
    v      = volumes.astype(float)

    if len(c) < 60:
        return 0.0, {"error": "資料不足60日"}

    # 條件1：低量橫盤（近 60 日內找連續 20 日低量整理段）
    avg_vol_60 = np.mean(v[-60:])
    low_vol_threshold = avg_vol_60 * 0.5
    consecutive_low   = 0
    max_consecutive   = 0
    for vol in v[-60:]:
        if vol < low_vol_threshold:
            consecutive_low += 1
            max_consecutive  = max(max_consecutive, consecutive_low)
        else:
            consecutive_low = 0

    if max_consecutive >= 20:
        score += 10
        detail["低量橫盤"] = f"連續{max_consecutive}日低量 (+10)"
    elif max_consecutive >= 10:
        score += 5
        detail["低量橫盤"] = f"連續{max_consecutive}日低量 (+5)"
    else:
        detail["低量橫盤"] = f"最長{max_consecutive}日 (0)"

    # 條件2：均線糾結
    if len(c) >= 60:
        ma5  = np.mean(c[-5:])
        ma20 = np.mean(c[-20:])
        ma60 = np.mean(c[-60:])
        spread = (max(ma5, ma20, ma60) - min(ma5, ma20, ma60)) / min(ma5, ma20, ma60) * 100
        if spread < 3.0:
            score += 5
            detail["均線糾結"] = f"三線價差{spread:.1f}% < 3% (+5)"
        else:
            detail["均線糾結"] = f"三線價差{spread:.1f}% (0)"

    # 條件3：近 20 日振幅
    if len(c) >= 20:
        high_20 = float(prices["high"].values[-20:].max())
        low_20  = float(prices["low"].values[-20:].min())
        amp_20  = (high_20 - low_20) / low_20 * 100
        if amp_20 < 10.0:
            score += 5
            detail["20日振幅"] = f"{amp_20:.1f}% < 10% (+5)"
        else:
            detail["20日振幅"] = f"{amp_20:.1f}% (0)"

    return min(score, 20.0), detail


# ══════════════════════════════════════════════════════════════
# 特徵二：第一根大量紅 K（最高 25 分）
# ══════════════════════════════════════════════════════════════
def _score_explosive_candle(
    prices: pd.DataFrame,
    volumes: np.ndarray
) -> tuple[float, dict]:
    """
    評估最近是否出現爆量紅 K 突破：
    1. 當日量 > 20日均量 × 3 倍      → +10 分
    2. 實體長紅 K（漲幅 > 3%）        → +8 分
    3. 股價突破近 60 日最高           → +7 分
    """
    score  = 0.0
    detail = {}
    c      = prices["close"].values.astype(float)
    o      = prices["open"].values.astype(float)
    h      = prices["high"].values.astype(float)
    v      = volumes.astype(float)

    if len(c) < 21:
        return 0.0, {"error": "資料不足"}

    # 最近 5 個交易日內找最強爆量紅 K
    best_score   = 0.0
    best_day_idx = -1
    for i in range(1, min(6, len(c))):
        idx = -(i)
        if idx < -len(c) + 20:
            break
        day_vol   = v[idx]
        avg_vol_20= np.mean(v[idx-20:idx])
        vol_ratio = day_vol / (avg_vol_20 + 1e-9)
        day_chg   = (c[idx] - c[idx-1]) / (c[idx-1] + 1e-9) * 100
        body      = abs(c[idx] - o[idx])
        amplitude = abs(h[idx] - prices["low"].values[idx])
        body_ratio= body / (amplitude + 1e-9)

        day_score = 0.0
        if vol_ratio >= 3.0:   day_score += 10
        elif vol_ratio >= 2.0: day_score += 5
        if day_chg > 3.0 and body_ratio > 0.6: day_score += 8
        elif day_chg > 1.5:                     day_score += 4

        if day_score > best_score:
            best_score   = day_score
            best_day_idx = idx
            detail["爆量倍數"] = f"{vol_ratio:.1f}倍均量"
            detail["漲幅"]     = f"{day_chg:.1f}%"
            detail["實體比"]   = f"{body_ratio*100:.0f}%"

    score += min(best_score, 18.0)

    # 條件3：是否突破近 60 日最高
    if len(c) >= 61:
        high_60 = float(h[-61:-1].max())
        if c[-1] > high_60:
            score += 7
            detail["突破60日高點"] = f"突破 {high_60:.1f} (+7)"
        elif c[-1] > float(h[-31:-1].max()):
            score += 3
            detail["突破30日高點"] = "(+3)"
        else:
            detail["突破前高"] = "尚未突破 (0)"

    return min(score, 25.0), detail


# ══════════════════════════════════════════════════════════════
# 特徵三：MACD 翻紅 + 零軸附近黃金交叉（最高 20 分）
# ══════════════════════════════════════════════════════════════
def _score_macd_golden(
    closes: np.ndarray
) -> tuple[float, dict]:
    """
    MACD 翻紅評分：
    1. 柱狀由負轉正（翻紅）          → +8 分
    2. DIF 在零軸下方 5% 範圍內交叉  → +7 分
    3. 近 60 日第一次翻紅            → +5 分
    """
    score  = 0.0
    detail = {}
    c      = closes.astype(float)

    if len(c) < 35:
        return 0.0, {"error": "資料不足"}

    # 計算 MACD（EMA12 - EMA26，Signal EMA9）
    def ema(data, period):
        k   = 2.0 / (period + 1)
        out = np.zeros(len(data))
        out[0] = data[0]
        for i in range(1, len(data)):
            out[i] = data[i] * k + out[i-1] * (1-k)
        return out

    ema12  = ema(c, 12)
    ema26  = ema(c, 26)
    dif    = ema12 - ema26
    signal = ema(dif, 9)
    hist   = dif - signal

    # 條件1：柱狀翻紅（今日為正，昨日為負）
    if len(hist) >= 2 and hist[-1] > 0 and hist[-2] < 0:
        score += 8
        detail["MACD翻紅"] = f"柱狀由{hist[-2]:.4f}翻正{hist[-1]:.4f} (+8)"
    elif hist[-1] > 0:
        detail["MACD狀態"] = "已在正值區"
    else:
        detail["MACD狀態"] = f"柱狀仍為負值{hist[-1]:.4f}"

    # 條件2：DIF 在零軸附近（距零軸 5% 內）交叉
    price_range = float(c[-1])
    zero_band   = price_range * 0.001   # 相對零軸帶
    if abs(dif[-1]) < abs(c[-1]) * 0.02 and hist[-1] > 0 and hist[-2] < 0:
        score += 7
        detail["零軸附近交叉"] = f"DIF={dif[-1]:.4f}（零軸附近）(+7)"
    elif hist[-1] > 0 and hist[-2] < 0:
        detail["交叉位置"] = "非零軸附近，效力稍弱"

    # 條件3：近 60 日第一次翻紅
    if len(hist) >= 60:
        prev_60_hist = hist[-61:-2]
        prev_positive_count = (prev_60_hist > 0).sum()
        if prev_positive_count == 0 and hist[-1] > 0:
            score += 5
            detail["首次翻紅"] = "近60日第一次翻紅，爆發力強 (+5)"
        elif prev_positive_count <= 3:
            score += 2
            detail["翻紅次數"] = f"近60日翻紅{prev_positive_count}次"

    return min(score, 20.0), detail


# ══════════════════════════════════════════════════════════════
# 特徵四：月線翻揚（最高 20 分）
# ══════════════════════════════════════════════════════════════
def _score_ma_golden_cross(
    closes: np.ndarray
) -> tuple[float, dict]:
    """
    均線翻揚評分：
    1. 日線 5MA 上穿 20MA（黃金交叉）  → +8 分
    2. 20MA 由下彎轉走平或上揚         → +7 分
    3. 股價站上 60MA 且 60MA 轉平      → +5 分
    """
    score  = 0.0
    detail = {}
    c      = closes.astype(float)

    if len(c) < 62:
        return 0.0, {"error": "資料不足"}

    def sma(data, n):
        return np.array([np.mean(data[i-n:i]) for i in range(n, len(data)+1)])

    ma5  = sma(c, 5)
    ma20 = sma(c, 20)
    ma60 = sma(c, 60)

    # 條件1：5MA 上穿 20MA（今日 5MA > 20MA，昨日 5MA < 20MA）
    ma5_aligned  = ma5[-len(ma20):]
    if len(ma5_aligned) >= 2 and len(ma20) >= 2:
        golden_cross_5_20 = (
            ma5_aligned[-1] > ma20[-1] and
            ma5_aligned[-2] < ma20[-2]
        )
        ma5_above_20 = ma5_aligned[-1] > ma20[-1]

        if golden_cross_5_20:
            score += 8
            detail["5MA上穿20MA"] = "今日發生黃金交叉 (+8)"
        elif ma5_above_20:
            score += 4
            detail["5MA上穿20MA"] = "5MA已在20MA上方 (+4)"
        else:
            detail["均線狀態"] = "5MA 仍在 20MA 下方 (0)"

    # 條件2：20MA 趨勢（近 5 日 20MA 斜率）
    if len(ma20) >= 6:
        slope_20 = (ma20[-1] - ma20[-6]) / ma20[-6] * 100
        if slope_20 > 0.5:
            score += 7
            detail["20MA趨勢"] = f"上揚 +{slope_20:.2f}% (+7)"
        elif slope_20 > -0.1:
            score += 4
            detail["20MA趨勢"] = f"走平 {slope_20:.2f}% (+4)"
        else:
            detail["20MA趨勢"] = f"仍在下彎 {slope_20:.2f}% (0)"

    # 條件3：股價站上 60MA 且 60MA 轉平
    if len(ma60) >= 6:
        price_above_60ma = c[-1] > ma60[-1]
        slope_60 = (ma60[-1] - ma60[-6]) / ma60[-6] * 100
        if price_above_60ma and slope_60 > -0.1:
            score += 5
            detail["60MA狀態"] = f"站上60MA且轉平 (+5)"
        elif price_above_60ma:
            score += 2
            detail["60MA狀態"] = "站上60MA但仍下彎 (+2)"
        else:
            detail["60MA狀態"] = "尚未站上60MA (0)"

    return min(score, 20.0), detail


# ══════════════════════════════════════════════════════════════
# 特徵五：突破前高（最高 15 分）
# ══════════════════════════════════════════════════════════════
def _score_breakout(
    prices: pd.DataFrame,
    volumes: np.ndarray
) -> tuple[float, dict]:
    """
    突破前高評分：
    1. 收盤突破近 120 日最高點  → +8 分
    2. 突破時成交量 > 均量 2 倍 → +4 分
    3. 突破後隔日不回填         → +3 分
    """
    score  = 0.0
    detail = {}
    c      = prices["close"].values.astype(float)
    h      = prices["high"].values.astype(float)
    v      = volumes.astype(float)

    if len(c) < 5:
        return 0.0, {"error": "資料不足"}

    # 條件1：突破近 120 日最高（排除最近 1 日）
    lookback = min(120, len(h) - 1)
    high_120 = float(h[-lookback-1:-1].max())
    if c[-1] > high_120:
        score += 8
        detail["突破120日高點"] = f"突破 {high_120:.1f} (+8)"
    else:
        high_60 = float(h[-61:-1].max()) if len(h) >= 62 else high_120
        if c[-1] > high_60:
            score += 4
            detail["突破60日高點"] = f"突破 {high_60:.1f} (+4)"
        else:
            detail["突破狀態"] = "尚未突破前高 (0)"

    # 條件2：突破時量能
    if len(v) >= 21:
        avg_vol_20 = np.mean(v[-21:-1])
        vol_ratio  = v[-1] / (avg_vol_20 + 1e-9)
        if vol_ratio >= 2.0:
            score += 4
            detail["突破量能"] = f"量比{vol_ratio:.1f}倍 (+4)"
        elif vol_ratio >= 1.5:
            score += 2
            detail["突破量能"] = f"量比{vol_ratio:.1f}倍 (+2)"
        else:
            detail["突破量能"] = f"量比{vol_ratio:.1f}倍（偏低）(0)"

    # 條件3：突破後不回填（今日收盤 > 昨日突破點 × 0.98）
    if len(c) >= 3 and score >= 8:
        if c[-1] >= c[-2] * 0.98:
            score += 3
            detail["突破確認"] = "突破後未回填 (+3)"
        else:
            detail["突破確認"] = "突破後有回測 (0)"

    return min(score, 15.0), detail


# ══════════════════════════════════════════════════════════════
# 4 階段模型判斷
# ══════════════════════════════════════════════════════════════
def _detect_stage(
    prices: pd.DataFrame,
    volumes: np.ndarray,
    flying_score: float
) -> tuple[int, str, str]:
    """
    判斷目前處於飆股的哪個階段：
    第一階段：主力吸籌（橫盤低量）
    第二階段：爆量發動（第一根大量紅K出現）
    第三階段：主升段（沿5MA上攻）
    第四階段：全民瘋狂（過熱警告）
    回傳：（階段編號, 階段名稱, 操作建議）
    """
    c = prices["close"].values.astype(float)
    v = volumes.astype(float)
    h = prices["high"].values.astype(float)

    if len(c) < 60:
        return 0, "資料不足", "資料累積中"

    avg_vol_60  = np.mean(v[-60:])
    avg_vol_5   = np.mean(v[-5:])
    vol_ratio   = avg_vol_5 / (avg_vol_60 + 1e-9)
    chg_20d     = (c[-1] - c[-21]) / (c[-21] + 1e-9) * 100
    ma5         = np.mean(c[-5:])
    ma20        = np.mean(c[-20:])
    ma60        = np.mean(c[-60:]) if len(c) >= 60 else ma20

    # 第四階段判斷：過熱
    is_overheated = (
        vol_ratio > 5.0 and       # 量能爆增 5 倍以上
        chg_20d > 30.0 and        # 20 日漲幅 > 30%
        c[-1] > ma5 * 1.05        # 股價過度偏離 5MA
    )
    if is_overheated:
        return 4, "全民瘋狂（第四階段）", (
            "⚠️ 過熱警告！股價短期漲幅過大，主力可能出貨，"
            "建議分批停利，新資金暫勿追高"
        )

    # 第三階段：主升段
    is_main_uptrend = (
        c[-1] > ma5 > ma20 > ma60 and   # 多頭排列
        vol_ratio > 1.5 and              # 量能仍在放大
        chg_20d > 10.0                   # 20 日漲幅 > 10%
    )
    if is_main_uptrend:
        return 3, "主升段（第三階段）", (
            "✅ 主升段進行中，沿 5MA 操作，"
            "回測 5MA 不破可持續持有，跌破 5MA 減碼"
        )

    # 第二階段：爆量發動
    recent_vol_max = float(v[-5:].max())
    is_launching   = (
        recent_vol_max > avg_vol_60 * 2.5 and   # 近 5 日有爆量
        c[-1] > ma20 and                          # 站上 20MA
        flying_score >= 60                         # 飆股基因成形
    )
    if is_launching:
        return 2, "爆量發動（第二階段）", (
            "🚀 起漲訊號出現！這只是起漲點而非追高點，"
            "可在爆量紅K隔日回測時分批進場，目標前高上方"
        )

    # 第一階段：主力吸籌
    is_accumulating = (
        vol_ratio < 0.8 and      # 量能低迷
        abs(chg_20d) < 8.0 and   # 20 日漲跌幅 < 8%
        flying_score >= 10        # 有一定整理條件
    )
    if is_accumulating:
        return 1, "主力吸籌（第一階段）", (
            "👀 主力可能正在悄悄吸籌，暫時沒人關注，"
            "等待爆量訊號出現再進場，不要急著追"
        )

    return 0, "訊號未明確", "暫時觀察，等待條件成熟"


# ══════════════════════════════════════════════════════════════
# 主函數：計算單一個股飆股基因評分
# ══════════════════════════════════════════════════════════════
def compute_flying_stock_score(stock_id: str) -> dict:
    """
    計算飆股基因評分（0~100 分）
    回傳完整分析結果字典
    """
    try:
        prices = query(f"""
            SELECT date, open, high, low, close, volume
            FROM daily_price
            WHERE stock_id = '{stock_id}'
            AND volume > 0
            ORDER BY date DESC LIMIT 130
        """).sort_values("date").reset_index(drop=True)

        if len(prices) < 30:
            return {
                "stock_id":      stock_id,
                "flying_score":  0.0,
                "stage":         0,
                "stage_name":    "資料不足",
                "signal":        "資料累積中",
                "grade":         "—",
                "details":       {},
                "sub_scores":    {},
            }

        volumes = prices["volume"].values.astype(float)
        closes  = prices["close"].values.astype(float)

        # 計算 5 個特徵分數
        s1, d1 = _score_consolidation(prices, volumes)
        s2, d2 = _score_explosive_candle(prices, volumes)
        s3, d3 = _score_macd_golden(closes)
        s4, d4 = _score_ma_golden_cross(closes)
        s5, d5 = _score_breakout(prices, volumes)

        total_score = s1 + s2 + s3 + s4 + s5

        # 階段判斷
        stage, stage_name, action = _detect_stage(
            prices, volumes, total_score
        )

        # 等級判斷
        if total_score >= FLYING_SCORE_STRONG:
            grade = "強力飆股訊號"
        elif total_score >= FLYING_SCORE_FORMING:
            grade = "條件成形中"
        elif total_score >= FLYING_SCORE_WATCH:
            grade = "持續追蹤"
        else:
            grade = "基因不足"

        # 過熱警告（第四階段）
        if stage == 4:
            grade = "⚠️ 過熱警告"

        return {
            "stock_id":     stock_id,
            "flying_score": round(total_score, 1),
            "stage":        stage,
            "stage_name":   stage_name,
            "action":       action,
            "grade":        grade,
            "sub_scores": {
                "橫盤整理": round(s1, 1),
                "爆量紅K":  round(s2, 1),
                "MACD翻紅": round(s3, 1),
                "月線翻揚": round(s4, 1),
                "突破前高": round(s5, 1),
            },
            "details": {**d1, **d2, **d3, **d4, **d5},
        }

    except Exception as e:
        logging.warning(f"[FlyingStock] {stock_id} 計算失敗：{e}")
        return {
            "stock_id":     stock_id,
            "flying_score": 0.0,
            "stage":        0,
            "stage_name":   "計算失敗",
            "action":       str(e),
            "grade":        "—",
            "sub_scores":   {},
            "details":      {},
        }
