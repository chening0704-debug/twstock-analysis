# engine/deep_analysis.py
# 深度股票分析引擎（8大模組，使用 Google Gemini API 免費版）
import os
import logging
import time
import requests
import pandas as pd
from db import query

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com"
    "/v1beta/models/gemini-1.5-flash:generateContent"
)
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "")


def _call_gemini(prompt: str, max_tokens: int = 1500) -> str:
    """呼叫 Google Gemini API 產生分析內容"""
    if not GEMINI_API_KEY:
        return "（需要設定 GEMINI_API_KEY）"
    try:
        url = f"{GEMINI_URL}?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature":     0.7,
            }
        }
        r = requests.post(url, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        return (data["candidates"][0]["content"]
                    ["parts"][0]["text"])
    except Exception as e:
        logging.error(f"[Gemini API] 失敗：{e}")
        return f"分析暫時無法取得（{e}）"


def _get_stock_name(stock_id: str) -> str:
    df = query(f"""
        SELECT stock_name FROM stock_universe
        WHERE stock_id = '{stock_id}' LIMIT 1
    """)
    if not df.empty and df["stock_name"].iloc[0]:
        return str(df["stock_name"].iloc[0])
    return stock_id


def _get_financial_data(stock_id: str) -> dict:
    data = {}

    # 近期股價
    price = query(f"""
        SELECT date, open, high, low, close, volume
        FROM daily_price
        WHERE stock_id = '{stock_id}'
        ORDER BY date DESC LIMIT 60
    """)
    if not price.empty:
        data["current_price"]  = float(price["close"].iloc[0])
        data["price_60d_ago"]  = float(price["close"].iloc[-1])
        data["price_chg_60d"]  = round(
            (data["current_price"] /
             data["price_60d_ago"] - 1) * 100, 2
        )
        data["avg_volume"]     = int(price["volume"].mean())
        data["price_high_60d"] = float(price["high"].max())
        data["price_low_60d"]  = float(price["low"].min())

    # 季財報
    fin = query(f"""
        SELECT year_quarter, eps, gross_margin, op_margin,
               net_margin, roe, roa, debt_ratio, per, pbr
        FROM quarterly_financial
        WHERE stock_id = '{stock_id}'
        ORDER BY year_quarter DESC LIMIT 8
    """)
    if not fin.empty:
        latest = fin.iloc[0]
        data["eps"]          = float(latest["eps"]          or 0)
        data["gross_margin"] = float(latest["gross_margin"] or 0)
        data["op_margin"]    = float(latest["op_margin"]    or 0)
        data["net_margin"]   = float(latest["net_margin"]   or 0)
        data["roe"]          = float(latest["roe"]          or 0)
        data["roa"]          = float(latest["roa"]          or 0)
        data["debt_ratio"]   = float(latest["debt_ratio"]   or 0)
        data["per"]          = float(latest["per"]          or 0)
        data["pbr"]          = float(latest["pbr"]          or 0)
        data["year_quarter"] = str(latest["year_quarter"])
        if len(fin) >= 4:
            eps_trend = fin["eps"].iloc[:4].tolist()
            data["eps_trend"]  = [float(e or 0) for e in eps_trend]
            data["eps_growth"] = round(
                (data["eps_trend"][0] /
                 (data["eps_trend"][-1] + 1e-9) - 1) * 100, 2
            )

    # 月營收
    rev = query(f"""
        SELECT year_month, revenue, yoy, mom
        FROM monthly_revenue
        WHERE stock_id = '{stock_id}'
        ORDER BY year_month DESC LIMIT 12
    """)
    if not rev.empty:
        data["latest_revenue"]  = int(rev["revenue"].iloc[0]  or 0)
        data["revenue_yoy"]     = float(rev["yoy"].iloc[0]    or 0)
        data["revenue_mom"]     = float(rev["mom"].iloc[0]    or 0)
        data["avg_revenue_yoy"] = round(
            float(rev["yoy"].mean() or 0), 2
        )

    # 三大法人
    inst = query(f"""
        SELECT date, foreign_net, trust_net, dealer_net
        FROM institutional_netbuy
        WHERE stock_id = '{stock_id}'
        ORDER BY date DESC LIMIT 10
    """)
    if not inst.empty:
        data["foreign_net_10d"] = int(inst["foreign_net"].sum() or 0)
        data["trust_net_10d"]   = int(inst["trust_net"].sum()   or 0)

    # 今日評分
    score = query(f"""
        SELECT score_total, score_fundamental, score_technical,
               score_chip, rf_prob_up, signal,
               target_price, stop_loss
        FROM daily_score
        WHERE stock_id = '{stock_id}'
        ORDER BY date DESC LIMIT 1
    """)
    if not score.empty:
        s = score.iloc[0]
        data["score_total"]       = float(s["score_total"]       or 0)
        data["score_fundamental"] = float(s["score_fundamental"] or 0)
        data["score_technical"]   = float(s["score_technical"]   or 0)
        data["score_chip"]        = float(s["score_chip"]        or 0)
        data["rf_prob_up"]        = float(s["rf_prob_up"]        or 0.5)
        data["signal"]            = str(s["signal"]              or "HOLD")
        data["target_price"]      = float(s["target_price"]      or 0)
        data["stop_loss"]         = float(s["stop_loss"]         or 0)

    return data


def _make_prompt_base(stock_id, stock_name, data) -> str:
    """產生共用財務數據背景資訊"""
    eps_trend = data.get("eps_trend", [])
    eps_str   = " → ".join([f"{e:.2f}" for e in reversed(eps_trend)]) \
                if eps_trend else "資料建立中"
    return f"""
股票代號：{stock_id}
股票名稱：{stock_name}
現價：{data.get('current_price','N/A')} 元
60日漲跌：{data.get('price_chg_60d','N/A')}%
60日最高：{data.get('price_high_60d','N/A')} 元
60日最低：{data.get('price_low_60d','N/A')} 元
EPS近4季（舊→新）：{eps_str}
EPS成長率：{data.get('eps_growth','N/A')}%
毛利率：{data.get('gross_margin','N/A')}%
營業利益率：{data.get('op_margin','N/A')}%
淨利率：{data.get('net_margin','N/A')}%
ROE：{data.get('roe','N/A')}%
ROA：{data.get('roa','N/A')}%
負債比率：{data.get('debt_ratio','N/A')}%
本益比(PER)：{data.get('per','N/A')}
股價淨值比(PBR)：{data.get('pbr','N/A')}
月營收年增率：{data.get('revenue_yoy','N/A')}%
12月平均營收年增率：{data.get('avg_revenue_yoy','N/A')}%
系統綜合評分：{data.get('score_total','N/A')}/100
系統訊號：{data.get('signal','N/A')}
RF預測漲機率：{data.get('rf_prob_up',0.5)*100:.0f}%
系統目標價：{data.get('target_price','N/A')} 元
系統停損價：{data.get('stop_loss','N/A')} 元
外資10日買賣超：{data.get('foreign_net_10d','N/A')} 張
投信10日買賣超：{data.get('trust_net_10d','N/A')} 張
"""


def analyze_module_1(sid, name, data) -> str:
    base = _make_prompt_base(sid, name, data)
    return _call_gemini(f"""
你是華爾街資深股票分析師，請用繁體中文針對以下台灣股票進行完整分析。
{base}
請提供（每項不超過100字）：
1.【商業模式】收入來源與核心業務
2.【競爭優勢】護城河分析
3.【產業趨勢】所屬產業的發展方向
4.【財務評估】依據上方數據評估財務健康
5.【關鍵風險】列出3個主要風險
6.【12-24月展望】未來走勢預測
請用數字標題，直接給分析內容。
""", 1200)


def analyze_module_2(sid, name, data) -> str:
    base = _make_prompt_base(sid, name, data)
    return _call_gemini(f"""
你是資深財務分析師，請用繁體中文分析以下台灣股票的財務狀況。
{base}
請分析（每項不超過80字）：
1.【營收成長】評估成長動能
2.【獲利能力】毛利率、淨利率評估
3.【財務結構】負債比率、ROE評估
4.【綜合判斷】財務體質「正在變強」還是「開始走弱」？原因一句話
""", 800)


def analyze_module_3(sid, name, data) -> str:
    base = _make_prompt_base(sid, name, data)
    return _call_gemini(f"""
你是企業競爭力分析師，請用繁體中文評估以下台灣股票的競爭護城河。
{base}
請評估（每項不超過60字）：
1.【品牌影響力】
2.【網路效應】
3.【轉換成本】
4.【成本優勢】
5.【專利技術】
6.【護城河評分】X/10分，評分理由一句話
""", 700)


def analyze_module_4(sid, name, data) -> str:
    base = _make_prompt_base(sid, name, data)
    return _call_gemini(f"""
你是投資銀行估值分析師，請用繁體中文對以下台灣股票進行估值分析。
{base}
請分析（每項不超過80字，需給出具體數字）：
1.【PER評估】與台股同業比較
2.【PBR評估】合理淨值比區間
3.【合理價區間】估算合理股價區間
4.【估值結論】目前股價「被低估」「合理」還是「高估」？
""", 700)


def analyze_module_5(sid, name, data) -> str:
    base = _make_prompt_base(sid, name, data)
    return _call_gemini(f"""
你是成長股研究分析師，請用繁體中文評估以下台灣股票的成長潛力。
{base}
請評估（每項不超過80字）：
1.【市場規模】產業市場規模評估
2.【成長動能】公司成長驅動因素
3.【AI與科技優勢】技術領先性
4.【5年成長預估】具體成長空間預測
5.【成長評級】強 / 中 / 弱，原因一句話
""", 700)


def analyze_module_6(sid, name, data) -> str:
    base = _make_prompt_base(sid, name, data)
    return _call_gemini(f"""
你是資深技術分析師，請用繁體中文對以下台灣股票進行技術分析。
{base}
請提供（需給出明確價格數字）：
1.【趨勢判斷】目前多頭/空頭/盤整
2.【最佳買入區間】勝算80%以上的買入價位
3.【目標獲利價】短期/中期/長期目標價
4.【嚴格停損價】停損設定與邏輯
5.【操作建議】一句話總結
""", 700)


def analyze_module_7(sid, name, data) -> str:
    base = _make_prompt_base(sid, name, data)
    return _call_gemini(f"""
你是資深投資顧問，請用繁體中文評估是否應該投資以下台灣股票。
{base}
請評估（每項不超過80字）：
1.【短期展望（1年內）】看多/中性/看空 + 理由
2.【長期展望（5年以上）】看多/中性/看空 + 理由
3.【關鍵催化因素】3個最重要的催化劑
4.【主要風險】3個最重要的風險
5.【最終結論】【買入】【持有】或【避免】+ 一句理由
""", 900)


def analyze_module_8(sid, name, data) -> str:
    base = _make_prompt_base(sid, name, data)
    return _
