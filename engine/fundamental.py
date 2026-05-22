# engine/fundamental.py — 基本面計分（權重 35%）
import logging
from db import query


def compute_fundamental_score(stock_id: str) -> float:
    score = 0.0

    # 月營收 YoY 連三月正成長
    try:
        rev = query(f"""
            SELECT yoy FROM monthly_revenue
            WHERE stock_id='{stock_id}'
            ORDER BY year_month DESC LIMIT 3
        """)["yoy"].values
        if len(rev) >= 3 and all(r > 0 for r in rev):
            score += 15
    except Exception:
        pass

    # 季財報各項指標
    try:
        fin = query(f"""
            SELECT eps, roe, gross_margin,
                   debt_ratio, fcf, per
            FROM quarterly_financial
            WHERE stock_id='{stock_id}'
            ORDER BY year_quarter DESC LIMIT 4
        """)

        if len(fin) >= 2:
            eps_now  = fin["eps"].iloc[0]
            eps_prev = fin["eps"].iloc[1]
            if eps_prev != 0:
                qoq = (eps_now - eps_prev) / abs(eps_prev)
                if qoq > 0.10:
                    score += 12
            if all(fin["eps"].iloc[:2] < 0):
                score -= 15

        if len(fin) >= 1:
            r = fin.iloc[0]
            if r["roe"] > 15:
                score += 10
            if r["gross_margin"] > 30:
                score += 8
            if r["fcf"] is not None and r["fcf"] > 0:
                score += 8
            if r["debt_ratio"] > 60:
                score -= 10
            if r["per"] is not None and 0 < r["per"] < 15:
                score += 10
    except Exception as e:
        logging.warning(f"[fundamental] {stock_id} 財報計算失敗：{e}")

    return max(0.0, min(100.0, score / 63.0 * 100))
