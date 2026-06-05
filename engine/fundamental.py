# engine/fundamental.py — 基本面計分 v2
# 改用 TWSE OpenAPI 免費資料，不依賴 FinMind 付費財報
import logging
import numpy as np
from db import query


def compute_fundamental_score(stock_id: str) -> float:
    score = 0.0
    has_data = False

    # ── 1. PER / PBR（來自 TWSE 每日更新）────────────────────
    try:
        fin = query(f"""
            SELECT per, pbr, eps, roe, gross_margin,
                   debt_ratio, net_margin
            FROM quarterly_financial
            WHERE stock_id = '{stock_id}'
            ORDER BY year_quarter DESC LIMIT 4
        """)

        if not fin.empty:
            has_data = True
            r = fin.iloc[0]
            per = float(r["per"] or 0)
            pbr = float(r["pbr"] or 0)

            # PER 評分
            if 0 < per <= 12:
                score += 20
            elif 0 < per <= 18:
                score += 15
            elif 0 < per <= 25:
                score += 8
            elif per > 40:
                score -= 5

            # PBR 評分
            if 0 < pbr <= 1.5:
                score += 10
            elif 0 < pbr <= 3.0:
                score += 5

            # ROE
            roe = float(r["roe"] or 0)
            if roe > 20:
                score += 15
            elif roe > 15:
                score += 10
            elif roe > 10:
                score += 5
            elif roe < 0:
                score -= 10

            # 毛利率
            gm = float(r["gross_margin"] or 0)
            if gm > 40:
                score += 10
            elif gm > 25:
                score += 6
            elif gm > 15:
                score += 3

            # 負債比率
            dr = float(r["debt_ratio"] or 0)
            if 0 < dr < 40:
                score += 5
            elif dr > 70:
                score -= 8

    except Exception as e:
        logging.warning(f"[fundamental] {stock_id} 財報失敗：{e}")

    # ── 2. 月營收趨勢（TWSE / FinMind）──────────────────────
    try:
        rev = query(f"""
            SELECT yoy, mom FROM monthly_revenue
            WHERE stock_id = '{stock_id}'
            ORDER BY year_month DESC LIMIT 6
        """)

        if not rev.empty:
            has_data = True
            yoy_vals = [float(v) for v in rev["yoy"].values
                        if v is not None]

            if len(yoy_vals) >= 3:
                # 連續正成長
                if all(y > 0 for y in yoy_vals[:3]):
                    score += 15
                elif all(y > 0 for y in yoy_vals[:2]):
                    score += 8
                elif yoy_vals[0] > 0:
                    score += 4

                # 加速成長（YoY 逐月擴大）
                if (len(yoy_vals) >= 2 and
                        yoy_vals[0] > yoy_vals[1] > 0):
                    score += 5

                # 衰退連續
                if all(y < 0 for y in yoy_vals[:3]):
                    score -= 10

    except Exception as e:
        logging.warning(f"[fundamental] {stock_id} 月營收失敗：{e}")

    # ── 3. 價量基本面替代評分（若財報資料不足）───────────────
    if not has_data:
        try:
            # 用近期股價表現替代基本面評估
            prices = query(f"""
                SELECT close, volume FROM daily_price
                WHERE stock_id = '{stock_id}'
                AND volume > 0
                ORDER BY date DESC LIMIT 60
            """)

            if len(prices) >= 20:
                c   = prices["close"].values.astype(float)
                v   = prices["volume"].values.astype(float)

                # 近20日相對60日均量（資金關注度）
                avg_v_60 = np.mean(v)
                avg_v_20 = np.mean(v[:20])
                vol_ratio = avg_v_20 / (avg_v_60 + 1e-9)

                if vol_ratio > 1.5:
                    score += 20
                elif vol_ratio > 1.2:
                    score += 12
                elif vol_ratio > 0.8:
                    score += 6

                # 近20日價格趨勢
                chg_20 = (c[0] - c[19]) / (c[19] + 1e-9) * 100
                if chg_20 > 15:
                    score += 20
                elif chg_20 > 8:
                    score += 12
                elif chg_20 > 3:
                    score += 6
                elif chg_20 < -10:
                    score -= 8

                # 近5日是否在近60日高點附近
                high_60 = np.max(c)
                if c[0] >= high_60 * 0.95:
                    score += 10

                logging.debug(
                    f"[fundamental] {stock_id} "
                    f"使用價量替代評分：{score:.1f}"
                )

        except Exception as e:
            logging.warning(
                f"[fundamental] {stock_id} "
                f"替代評分失敗：{e}"
            )

    final = max(0.0, min(100.0, score))
    logging.debug(
        f"[fundamental] {stock_id} 最終分數：{final:.1f}"
    )
    return final
