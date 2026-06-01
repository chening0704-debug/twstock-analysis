# engine/industry_chain.py
# 上下游產業鏈連動分析
# 功能：
#   1. AI算力/AIDC題材自動標記
#   2. 上下游產業鏈連動評分
#   3. 國際AI龍頭股連動性追蹤
#   4. Fed降息週期判斷
#   5. 千張大戶 + 內部人動向評分

import logging
import requests
import pandas as pd
import numpy as np
from db import query

# ══════════════════════════════════════════════════════════════
# 台股產業鏈分類資料庫
# ══════════════════════════════════════════════════════════════
INDUSTRY_DB = {
    # AI 算力中心 / AIDC
    "AI算力": {
        "stocks": ["2438","6669","3711","2376","3034","6770"],
        "upstream":   ["AI伺服器供應商","GPU供應商"],
        "downstream": ["AI應用公司","雲端服務商"],
        "catalysts":  ["AI需求爆發","算力需求指數級成長",
                       "伺服器交期縮短","裝機速度加快"],
    },
    # 半導體製造
    "半導體製造": {
        "stocks": ["2330","2303","2344","3711","2454"],
        "upstream":   ["設備商","材料商","光罩廠"],
        "downstream": ["IC設計","系統廠","品牌廠"],
        "catalysts":  ["AI晶片需求","先進製程量產",
                       "CoWoS先進封裝","HBM需求"],
    },
    # IC 設計
    "IC設計": {
        "stocks": ["2454","3034","3533","6770","4966","2379"],
        "upstream":   ["晶圓代工","IP授權"],
        "downstream": ["系統廠","模組廠","品牌廠"],
        "catalysts":  ["AI Edge端需求","5G滲透率提升",
                       "車用電子成長"],
    },
    # 伺服器 / 網通
    "伺服器網通": {
        "stocks": ["2356","2382","3231","4977","6669","2376"],
        "upstream":   ["ODM零組件","電源供應器","散熱模組"],
        "downstream": ["雲端資料中心","企業IT","電信商"],
        "catalysts":  ["AI伺服器出貨量","GB200平台導入",
                       "液冷散熱需求"],
    },
    # 電源管理 / 被動元件
    "電源被動": {
        "stocks": ["2308","2317","2327","6239","3037"],
        "upstream":   ["原物料","銅箔基板"],
        "downstream": ["AI伺服器","電動車","儲能"],
        "catalysts":  ["AI用電需求大增","電動車滲透率",
                       "儲能建置加速"],
    },
    # 散熱 / 液冷
    "散熱液冷": {
        "stocks": ["3008","6230","1590","2059"],
        "upstream":   ["銅材","鋁材","泵浦"],
        "downstream": ["AI伺服器","資料中心"],
        "catalysts":  ["液冷滲透率提升","GB200高功耗需求",
                       "資料中心PUE要求"],
    },
}

# 熱門題材關鍵詞（從重大訊息自動偵測）
HOT_THEMES = {
    "AI算力":     ["AI","算力","AIDC","HPC","GPU","H100","H200",
                   "B200","GB200","CoreWeave"],
    "CoWoS":      ["CoWoS","先進封裝","3D封裝","SoIC"],
    "HBM":        ["HBM","高頻寬記憶體","HBM3","HBM3E"],
    "電動車":     ["電動車","EV","車用","ADAS","自駕"],
    "儲能":       ["儲能","ESS","電池","磷酸鐵鋰"],
    "降息受惠":   ["降息","Fed","利率","資本支出"],
    "庫藏股":     ["庫藏股","買回"],
    "法說會利多": ["法說會","業績優","超預期","調升目標價"],
}

# 國際AI龍頭股（用於連動性分析）
AI_LEADER_STOCKS = {
    "NVDA":  "NVIDIA（GPU龍頭）",
    "SMCI":  "SuperMicro（AI伺服器）",
    "DELL":  "Dell（伺服器）",
    "META":  "Meta（AI應用）",
    "MSFT":  "Microsoft（雲端AI）",
    "GOOGL": "Google（雲端AI）",
    "CRWv":  "CoreWeave（AI算力）",
}


def get_stock_industry(stock_id: str) -> str:
    """判斷股票所屬產業"""
    for industry, data in INDUSTRY_DB.items():
        if stock_id in data["stocks"]:
            return industry
    return "其他"


def detect_themes(stock_id: str) -> list:
    """從重大訊息偵測熱門題材標籤"""
    themes = []
    try:
        df = query(f"""
            SELECT title FROM announcements
            WHERE stock_id = '{stock_id}'
            AND date >= date('now', '-30 days')
            ORDER BY announce_time DESC LIMIT 30
        """)
        if df.empty:
            return themes

        all_text = " ".join(df["title"].tolist())
        for theme, keywords in HOT_THEMES.items():
            if any(kw in all_text for kw in keywords):
                themes.append(theme)
    except Exception as e:
        logging.warning(f"[IndustryChain] {stock_id} 題材偵測失敗：{e}")

    return themes


def compute_chain_score(stock_id: str) -> dict:
    """
    產業鏈評分（最高 20 分）
    1. 屬於熱門產業鏈   → +8 分
    2. 偵測到熱門題材   → +6 分
    3. AI 相關供應鏈    → +6 分
    """
    score    = 0.0
    industry = get_stock_industry(stock_id)
    themes   = detect_themes(stock_id)
    detail   = {}

    # 產業鏈加分
    if industry != "其他":
        score += 8
        idata = INDUSTRY_DB.get(industry, {})
        detail["產業"] = industry
        detail["上游"] = "、".join(idata.get("upstream",   []))
        detail["下游"] = "、".join(idata.get("downstream", []))
        detail["催化劑"] = "、".join(idata.get("catalysts",  [])[:3])

    # 題材加分
    if themes:
        score += min(len(themes) * 2, 6)
        detail["偵測題材"] = "、".join(themes)

    # AI 相關特別加分
    ai_industries = ["AI算力", "半導體製造", "IC設計", "伺服器網通"]
    if industry in ai_industries or "AI算力" in themes:
        score += 6
        detail["AI加成"] = "AI供應鏈相關 (+6)"

    return {
        "chain_score": round(min(score, 20), 1),
        "industry":    industry,
        "themes":      themes,
        "detail":      detail,
    }


def get_international_linkage() -> dict:
    """
    取得國際AI龍頭股近期漲跌
    判斷對台股AI族群的連動影響
    """
    result = {
        "ai_sentiment": "中性",
        "score_adj":    0.0,
        "detail":       {},
    }
    try:
        import yfinance as yf
        import time as _time

        positive_count = 0
        negative_count = 0
        total_count    = 0

        for ticker, name in AI_LEADER_STOCKS.items():
            try:
                tk   = yf.Ticker(ticker)
                hist = tk.history(period="5d", auto_adjust=True)
                if hist.empty or len(hist) < 2:
                    continue
                c    = hist["Close"].dropna()
                chg  = float((c.iloc[-1]/c.iloc[-2]-1)*100)
                result["detail"][ticker] = {
                    "name": name,
                    "chg":  round(chg, 2),
                }
                if chg > 1.0:
                    positive_count += 1
                elif chg < -1.0:
                    negative_count += 1
                total_count += 1
                _time.sleep(0.5)
            except Exception:
                continue

        if total_count > 0:
            bull_ratio = positive_count / total_count
            bear_ratio = negative_count / total_count
            if bull_ratio >= 0.6:
                result["ai_sentiment"] = "AI族群偏多"
                result["score_adj"]    = 10.0
            elif bear_ratio >= 0.6:
                result["ai_sentiment"] = "AI族群偏空"
                result["score_adj"]    = -8.0
            else:
                result["ai_sentiment"] = "AI族群中性"
                result["score_adj"]    = 0.0

        logging.info(
            f"[IndustryChain] 國際AI連動："
            f"{result['ai_sentiment']} "
            f"多:{positive_count} 空:{negative_count}"
        )

    except Exception as e:
        logging.warning(f"[IndustryChain] 國際連動分析失敗：{e}")

    return result


def get_fed_cycle_score() -> float:
    """
    Fed 降息週期判斷
    依據 VIX + 美元指數趨勢判斷資金環境
    """
    score = 0.0
    try:
        macro = query("""
            SELECT vix, usd_twd FROM macro_daily
            ORDER BY date DESC LIMIT 10
        """)
        if macro.empty:
            return 0.0

        vix_now  = float(macro["vix"].iloc[0])
        vix_avg  = float(macro["vix"].mean())
        usd_now  = float(macro["usd_twd"].iloc[0])
        usd_prev = float(macro["usd_twd"].iloc[-1])

        # VIX 低位 = 市場穩定 = 資金環境友善
        if vix_now < 15:
            score += 8
        elif vix_now < 20:
            score += 5
        elif vix_now > 30:
            score -= 8

        # 台幣升值 = 外資匯入 = 降息受惠
        if usd_now < usd_prev * 0.998:
            score += 7
        elif usd_now > usd_prev * 1.002:
            score -= 5

    except Exception as e:
        logging.warning(f"[IndustryChain] Fed週期判斷失敗：{e}")

    return round(score, 1)


def compute_institutional_depth(stock_id: str) -> dict:
    """
    法人庫存深度分析
    法人庫存低位 = 未來補庫空間大 = 潛在買盤充足
    """
    result = {
        "inst_depth_score": 0.0,
        "inst_detail":      {},
    }
    try:
        inst = query(f"""
            SELECT date, foreign_net, trust_net, dealer_net
            FROM institutional_netbuy
            WHERE stock_id = '{stock_id}'
            ORDER BY date DESC LIMIT 60
        """)
        if inst.empty:
            return result

        # 計算累計法人淨買超（近60日）
        f_cum  = int(inst["foreign_net"].sum())
        t_cum  = int(inst["trust_net"].sum())
        f_avg  = float(inst["foreign_net"].mean())
        t_avg  = float(inst["trust_net"].mean())

        score = 0.0
        # 外資近60日累計買超
        if f_cum > 0:
            score += 8
            result["inst_detail"]["外資60日累計"] = f"+{f_cum:,}張（持續買入）"
        elif f_cum < -5000:
            score -= 5
            result["inst_detail"]["外資60日累計"] = f"{f_cum:,}張（持續賣出）"
        else:
            result["inst_detail"]["外資60日累計"] = f"{f_cum:,}張"

        # 投信近60日（投信庫存低 = 補庫空間大）
        if t_cum > 0:
            score += 7
            result["inst_detail"]["投信60日累計"] = f"+{t_cum:,}張"
        elif t_cum < 0 and abs(t_cum) > 1000:
            score += 5
            result["inst_detail"]["投信庫存"] = "低位，未來補庫空間大"

        # 近5日法人動向
        recent_f = int(inst["foreign_net"].iloc[:5].sum())
        recent_t = int(inst["trust_net"].iloc[:5].sum())
        if recent_f > 0 and recent_t > 0:
            score += 5
            result["inst_detail"]["近5日"] = "外資投信同步買超"
        elif recent_f > 0:
            result["inst_detail"]["近5日外資"] = f"+{recent_f:,}張"

        result["inst_depth_score"] = round(min(max(score, 0), 20), 1)

    except Exception as e:
        logging.warning(
            f"[IndustryChain] {stock_id} 法人深度失敗：{e}"
        )

    return result


def compute_full_chain_analysis(
    stock_id:         str,
    intl_linkage:     dict = None,
    fed_score:        float = 0.0,
) -> dict:
    """
    完整產業鏈分析（供 scorer.py 呼叫）
    整合：產業鏈 + 題材 + 法人深度
    """
    chain   = compute_chain_score(stock_id)
    inst_d  = compute_institutional_depth(stock_id)

    # 國際連動加成（只對AI族群有效）
    intl_adj = 0.0
    if intl_linkage and chain["industry"] in [
        "AI算力","半導體製造","IC設計","伺服器網通"
    ]:
        intl_adj = float(intl_linkage.get("score_adj", 0))

    total_chain_score = (
        chain["chain_score"]
        + inst_d["inst_depth_score"]
        + intl_adj
        + fed_score * 0.3
    )
    total_chain_score = round(
        min(max(total_chain_score, 0), 40), 1
    )

    return {
        "chain_score":      chain["chain_score"],
        "inst_depth_score": inst_d["inst_depth_score"],
        "intl_adj":         intl_adj,
        "total_chain":      total_chain_score,
        "industry":         chain["industry"],
        "themes":           chain["themes"],
        "chain_detail":     chain["detail"],
        "inst_detail":      inst_d["inst_detail"],
    }
