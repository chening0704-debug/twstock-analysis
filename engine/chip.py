# engine/chip.py — 籌碼面計分（權重 25%）
import logging
from db import query


def compute_chip_score(stock_id: str) -> float:
    score = 0.0

    # 三大法人
    try:
        inst = query(f"""
            SELECT foreign_net, trust_net, dealer_net
            FROM institutional_netbuy
            WHERE stock_id='{stock_id}'
            ORDER BY date DESC LIMIT 10
        """)

        if len(inst) >= 5:
            fnet = inst["foreign_net"].values
            tnet = inst["trust_net"].values

            # 外資連買 3 日
            if all(f > 0 for f in fnet[:3]):
                score += 18
            # 外資連賣 5 日
            if all(f < 0 for f in fnet[:5]):
                score -= 18
            # 投信連買 5 日
            if all(t > 0 for t in tnet[:5]):
                score += 15
            # 外資 + 投信同步買
            if fnet[0] > 0 and tnet[0] > 0:
                score += 12

    except Exception as e:
        logging.warning(f"[chip] {stock_id} 法人計算失敗：{e}")

    # 融資融券
    try:
        margin = query(f"""
            SELECT margin_balance, short_sell_borrow
            FROM margin_balance
            WHERE stock_id='{stock_id}'
            ORDER BY date DESC LIMIT 7
        """)

        if len(margin) >= 2:
            mb_now   = margin["margin_balance"].iloc[0]
            mb_prev  = margin["margin_balance"].iloc[-1]
            bor_now  = margin["short_sell_borrow"].iloc[0]
            bor_prev = margin["short_sell_borrow"].iloc[-1]

            mb_chg  = mb_now - mb_prev
            bor_chg = (bor_now / (bor_prev + 1) - 1) * 100

            # 融資減少：籌碼健康
            if mb_chg < 0:
                score += 10
            # 融資暴增：散戶追高
            if mb_chg > 5000:
                score -= 10
            # 借券回補：空方投降
            if bor_chg < -10:
                score += 8
            # 借券暴增：空方加碼
            if bor_chg > 30:
                score -= 15

    except Exception as e:
        logging.warning(f"[chip] {stock_id} 融資券計算失敗：{e}")

    return max(0.0, min(100.0, score / 63.0 * 100))
