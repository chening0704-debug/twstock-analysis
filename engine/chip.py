# engine/chip.py — 籌碼面計分 v2
# 修正：加入多層備援，確保有資料時不回傳0
import logging
import numpy as np
from db import query


def compute_chip_score(stock_id: str) -> float:
    score   = 0.0
    has_data= False

    # ── 1. 三大法人買賣超 ─────────────────────────────────────
    try:
        inst = query(f"""
            SELECT date, foreign_net, trust_net, dealer_net
            FROM institutional_netbuy
            WHERE stock_id = '{stock_id}'
            ORDER BY date DESC LIMIT 20
        """)

        if not inst.empty and len(inst) >= 1:
            has_data = True
            fnet = inst["foreign_net"].values.astype(float)
            tnet = inst["trust_net"].values.astype(float)
            dnet = inst["dealer_net"].values.astype(float)

            # 今日
            f1 = fnet[0]
            t1 = tnet[0]

            # 外資評分
            if f1 > 5000:
                score += 20
            elif f1 > 1000:
                score += 15
            elif f1 > 0:
                score += 8
            elif f1 < -5000:
                score -= 15
            elif f1 < -1000:
                score -= 8

            # 投信評分
            if t1 > 1000:
                score += 15
            elif t1 > 0:
                score += 8
            elif t1 < -1000:
                score -= 10

            # 連續買超天數（外資）
            if len(fnet) >= 5:
                buy_days = sum(1 for f in fnet[:5] if f > 0)
                sell_days= sum(1 for f in fnet[:5] if f < 0)
                if buy_days >= 4:
                    score += 12
                elif buy_days >= 3:
                    score += 7
                elif sell_days >= 4:
                    score -= 10

            # 投信連買
            if len(tnet) >= 3:
                t_buy = sum(1 for t in tnet[:3] if t > 0)
                if t_buy >= 3:
                    score += 10
                elif t_buy >= 2:
                    score += 5

            # 外資+投信同向（共振加分）
            if f1 > 0 and t1 > 0:
                score += 10
            elif f1 < 0 and t1 < 0:
                score -= 8

            logging.debug(
                f"[chip] {stock_id} 法人：外資{f1:.0f} "
                f"投信{t1:.0f} 分數{score:.1f}"
            )

    except Exception as e:
        logging.warning(f"[chip] {stock_id} 法人失敗：{e}")

    # ── 2. 融資融券 ───────────────────────────────────────────
    try:
        margin = query(f"""
            SELECT margin_balance, short_sell_borrow,
                   short_balance
            FROM margin_balance
            WHERE stock_id = '{stock_id}'
            ORDER BY date DESC LIMIT 10
        """)

        if not margin.empty and len(margin) >= 2:
            has_data = True
            mb_now   = float(margin["margin_balance"].iloc[0] or 0)
            mb_prev  = float(margin["margin_balance"].iloc[-1] or 1)
            bor_now  = float(margin["short_sell_borrow"].iloc[0] or 0)
            bor_prev = float(margin["short_sell_borrow"].iloc[-1] or 1)
            sb_now   = float(margin["short_balance"].iloc[0] or 0)

            # 融資變化
            mb_chg_pct = (mb_now - mb_prev) / (mb_prev + 1e-9) * 100
            if mb_chg_pct < -5:
                score += 8    # 融資大減 = 籌碼健康
            elif mb_chg_pct < 0:
                score += 4
            elif mb_chg_pct > 20:
                score -= 8    # 融資暴增 = 散戶追高

            # 借券回補（空方投降）
            bor_chg = (bor_now - bor_prev) / (bor_prev + 1e-9) * 100
            if bor_chg < -10:
                score += 8
            elif bor_chg > 30:
                score -= 8

    except Exception as e:
        logging.warning(f"[chip] {stock_id} 融資券失敗：{e}")

    # ── 3. 若無任何籌碼資料，用量能代替 ─────────────────────
    if not has_data:
        try:
            prices = query(f"""
                SELECT close, volume FROM daily_price
                WHERE stock_id = '{stock_id}'
                AND volume > 0
                ORDER BY date DESC LIMIT 20
            """)

            if len(prices) >= 5:
                v       = prices["volume"].values.astype(float)
                c       = prices["close"].values.astype(float)
                avg_v   = np.mean(v[1:])
                v_ratio = v[0] / (avg_v + 1e-9)

                # 量能異常放大
                if v_ratio >= 3.0:
                    score += 30
                elif v_ratio >= 2.0:
                    score += 20
                elif v_ratio >= 1.5:
                    score += 12
                elif v_ratio >= 1.2:
                    score += 6

                # 今日漲跌與量能配合
                day_chg = (c[0] - c[1]) / (c[1] + 1e-9) * 100
                if v_ratio >= 1.5 and day_chg > 2:
                    score += 15
                elif v_ratio >= 1.5 and day_chg < -2:
                    score -= 10

                logging.debug(
                    f"[chip] {stock_id} "
                    f"使用量能替代：量比{v_ratio:.1f}x "
                    f"分數{score:.1f}"
                )

        except Exception as e:
            logging.warning(
                f"[chip] {stock_id} 量能替代失敗：{e}"
            )

    final = max(0.0, min(100.0, score))
    logging.debug(
        f"[chip] {stock_id} 最終分數：{final:.1f}"
    )
    return final
