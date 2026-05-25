# engine/news.py — 消息面 NLP 計分（權重 5%）
import logging
from db import query

POS_KEYWORDS = [
    "庫藏股", "買回", "大幅成長", "創新高", "重大訂單",
    "新客戶", "超越預期", "轉虧為盈", "產能滿載", "合作協議",
    "獲利創高", "業績亮眼", "法說會正面", "獲得認證",
]
NEG_KEYWORDS = [
    "財報重編", "會計師保留意見", "違約", "遭調查",
    "董事長辭職", "重大虧損", "停工", "遭檢調", "裁員",
    "客戶取消", "產能利用率下滑", "庫存去化", "重大損失",
]


def compute_news_score(stock_id: str) -> float:
    try:
        df = query(f"""
            SELECT title FROM announcements
            WHERE stock_id='{stock_id}'
            AND date >= date('now', '-7 days')
            ORDER BY announce_time DESC LIMIT 20
        """)
    except Exception as e:
        logging.warning(f"[news] {stock_id} 查詢失敗：{e}")
        return 50.0

    if df.empty:
        return 50.0

    score    = 50.0
    all_text = " ".join(df["title"].tolist())

    for kw in POS_KEYWORDS:
        if kw in all_text:
            if kw in ["庫藏股", "買回"]:
                score += 30
            elif kw in ["重大訂單", "新客戶", "獲利創高"]:
                score += 15
            else:
                score += 10

    for kw in NEG_KEYWORDS:
        if kw in all_text:
            if kw in ["財報重編", "遭調查", "遭檢調"]:
                score -= 30
            elif kw in ["董事長辭職", "違約", "重大虧損"]:
                score -= 20
            else:
                score -= 10

    return max(0.0, min(100.0, score))
