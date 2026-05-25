# engine/macro.py — 總經面計分（權重 10%）
import logging
import numpy as np
from db import query


def compute_macro_score() -> float:
    score = 50.0

    try:
        macro = query(
            "SELECT * FROM macro_daily ORDER BY date DESC LIMIT 1"
        )
        if macro.empty:
            return 50.0
        macro = macro.iloc[0]

        # VIX 恐慌指數
        vix = float(macro["vix"])
        if vix < 15:
            score += 25
        elif vix < 20:
            score += 20
        elif vix > 30:
            score -= 25
        elif vix > 25:
            score -= 10

        # 費半 SOX 漲跌
        sox = float(macro["sox_chg_pct"])
        if sox > 3:
            score += 25
        elif sox > 1:
            score += 12
        elif sox < -3:
            score -= 20
        elif sox < -1:
            score -= 8

        # NVIDIA 漲跌（AI 供應鏈領先指標）
        nvda = float(macro["nvda_chg_pct"])
        if nvda > 3:
            score += 10
        elif nvda < -3:
            score -= 10

    except Exception as e:
        logging.warning(f"[macro] 計算失敗：{e}")
        return 50.0

    # 台幣匯率趨勢
    try:
        usd = query(
            "SELECT usd_twd FROM macro_daily "
            "ORDER BY date DESC LIMIT 5"
        )["usd_twd"].values
        if len(usd) >= 3 and usd[0] < usd[2]:
            score += 15   # 台幣升值，外資匯入訊號
    except Exception:
        pass

    return max(0.0, min(100.0, score))
