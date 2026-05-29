# engine/scorer.py — 主分析引擎（整合飆股基因）
import logging
import pickle
import pandas as pd
import numpy as np
from pathlib import Path
from db import query, upsert
from engine.fundamental import compute_fundamental_score
from engine.technical   import compute_technical_score
from engine.chip        import compute_chip_score
from engine.macro       import compute_macro_score
from engine.news        import compute_news_score
from engine.flying_stock import compute_flying_stock_score

MODEL_PATH  = Path("models/rf_model.pkl")
SCALER_PATH = Path("models/rf_scaler.pkl")

RULE_WEIGHTS = {
    "fundamental": 0.35,
    "technical":   0.25,
    "chip":        0.25,
    "macro":       0.10,
    "news":        0.05,
}


def check_system_readiness() -> dict:
    try:
        df   = query("SELECT COUNT(DISTINCT date) as cnt "
                     "FROM daily_price WHERE volume > 0")
        days = int(df["cnt"].iloc[0]) if not df.empty else 0
    except Exception:
        days = 0

    if days < 5:
        return {"mode":"accumulating","use_rf":False,
                "alpha":1.0,"beta":0.0,"days":days}
    elif days < 30:
        return {"mode":"warmup","use_rf":False,
                "alpha":0.85,"beta":0.15,"days":days}
    else:
        return {"mode":"full","use_rf":MODEL_PATH.exists(),
                "alpha":0.60,"beta":0.40,"days":days}


def load_rf_model():
    try:
        with open(MODEL_PATH,  "rb") as f: rf = pickle.load(f)
        with open(SCALER_PATH, "rb") as f: sc = pickle.load(f)
        return rf, sc
    except Exception:
        return None, None


def classify_signal(
    total, tech, chip, rf_prob,
    buy_thr=72, rf_min=0.55
) -> str:
    if (total >= buy_thr and tech >= 55
            and chip >= 55 and rf_prob >= rf_min):
        return "BUY"
    elif total >= buy_thr - 5 and (tech >= 50 or chip >= 50):
        return "BUY*"
    elif total >= 55:
        return "HOLD"
    elif total < 40 or (tech < 35 and chip < 35):
        return "CUT"
    return "SELL"


def analyze_portfolio(
    score_df:   pd.DataFrame,
    alpha:      float,
    beta:       float,
    flying_map: dict = None,
) -> list:
    try:
        holdings = query(
            "SELECT * FROM my_portfolio"
        ).to_dict("records")
    except Exception:
        return []
    if not holdings:
        return []

    advice = []
    for h in holdings:
        sid = h["stock_id"]
        row = score_df[score_df["stock_id"] == sid]
        if row.empty:
            continue

        r       = row.iloc[0]
        score   = r["score_total"]
        rf_prob = r["rf_prob_up"]
        st      = r["score_technical"]
        sc      = r["score_chip"]

        # 飆股基因加成
        flying_info  = flying_map.get(sid, {}) if flying_map else {}
        flying_score = float(flying_info.get("flying_score", 0))
        flying_stage = int(flying_info.get("stage", 0))
        flying_grade = flying_info.get("grade", "")

        try:
            price_r = query(f"""
                SELECT close FROM daily_price
                WHERE stock_id='{sid}'
                ORDER BY date DESC LIMIT 1
            """)
            if price_r.empty:
                continue
            current = float(price_r.iloc[0]["close"])
        except Exception:
            continue

        cost    = float(h["cost_price"])
        shares  = float(h["shares"])
        pnl_pct = (current - cost) / cost * 100

        # 第四階段過熱警告（優先判斷）
        if flying_stage == 4:
            signal = "停損" if pnl_pct < 0 else "出清"
            desc   = (
                f"🚨 飆股基因偵測到第四階段「全民瘋狂」！"
                f"評分{score:.0f}分，飆股分{flying_score:.0f}分，"
                f"建議立即分批停利，損益{pnl_pct:+.1f}%"
            )
        elif score >= 78 and rf_prob > 0.60 and pnl_pct > -5:
            add_sh   = max(0.1, round(shares * 0.3, 1))
            new_cost = (
                (cost * shares + current * add_sh)
                / (shares + add_sh)
            )
            signal = "加碼"
            desc   = (
                f"評分優異（{score:.0f}分），RF漲機率"
                f"{rf_prob*100:.0f}%"
                + (f"，飆股基因{flying_score:.0f}分【{flying_grade}】"
                   if flying_score >= 45 else "")
                + f"，建議加碼 {add_sh} 張，"
                  f"均成本→{new_cost:.1f}"
            )
        elif score >= 62 and rf_prob >= 0.50:
            signal = "持有"
            desc   = (
                f"評分良好（{score:.0f}分），"
                f"損益{pnl_pct:+.1f}%，續持觀察"
                + (f"，飆股訊號：{flying_grade}"
                   if flying_score >= 60 else "")
            )
        elif score < 45 and pnl_pct > 8:
            signal = "出清"
            desc   = (
                f"評分轉弱（{score:.0f}分），"
                f"建議獲利了結，損益{pnl_pct:+.1f}%"
            )
        elif score < 42 or pnl_pct < -8:
            signal = "停損"
            desc   = (
                f"🚨 停損出場！評分{score:.0f}分，"
                f"損益{pnl_pct:+.1f}%，風險控管優先"
            )
        elif st < 40 and sc < 40:
            signal = "減碼"
            desc   = (
                f"技術（{st:.0f}）+籌碼（{sc:.0f}）雙弱，"
                f"建議減碼50%"
            )
        else:
            signal = "觀察"
            desc   = (
                f"訊號未明確（{score:.0f}分），"
                f"靜待下一交易日確認"
            )

        advice.append({
            "stock_id":      sid,
            "name":          h.get("stock_name", sid),
            "cost":          cost,
            "current":       current,
            "shares":        shares,
            "pnl_pct":       round(pnl_pct, 2),
            "market_val":    int(current * shares * 1000),
            "score":         round(score, 1),
            "rf_prob":       round(rf_prob, 4),
            "flying_score":  round(flying_score, 1),
            "flying_grade":  flying_grade,
            "flying_stage":  flying_stage,
            "signal":        signal,
            "action_desc":   desc,
        })

    return sorted(advice, key=lambda x: x["score"], reverse=True)


def run_analysis_engine() -> dict:
    logging.info("主分析引擎啟動")

    readiness    = check_system_readiness()
    mode         = readiness["mode"]
    use_rf       = readiness["use_rf"]
    RULE_W_TOTAL = readiness["alpha"]
    RF_W         = readiness["beta"]

    logging.info(
        f"[Scorer] 模式={mode} 天數={readiness['days']} "
        f"α={RULE_W_TOTAL:.2f} β={RF_W:.2f}"
    )

    if mode == "accumulating":
        logging.info("資料累積期，不輸出推薦")
        return {
            "top10":        pd.DataFrame(),
            "top_flying":   [],
            "flying_scan":  [],
            "portfolio":    [],
            "macro_score":  50.0,
            "market_state": "資料累積中",
            "mode":         mode,
            "days":         readiness["days"],
        }

    # 取今日有效個股
    stocks = query("""
        SELECT DISTINCT stock_id FROM daily_price
        WHERE date = (SELECT MAX(date) FROM daily_price)
        AND volume > 0
    """)["stock_id"].tolist()
    logging.info(f"今日有效個股：{len(stocks)} 支")

    macro_score = compute_macro_score()
    rf, sc_model = (load_rf_model() if use_rf else (None, None))
    if use_rf and rf is None:
        logging.warning("RF 模型載入失敗，改用純規則式")
        use_rf       = False
        RULE_W_TOTAL = 1.0
        RF_W         = 0.0

    results      = []
    flying_all   = []

    for i, sid in enumerate(stocks):
        try:
            sf       = compute_fundamental_score(sid)
            st       = compute_technical_score(sid)
            sc_score = compute_chip_score(sid)
            sn       = compute_news_score(sid)

            score_rule = (
                sf * RULE_WEIGHTS["fundamental"]
                + st * RULE_WEIGHTS["technical"]
                + sc_score * RULE_WEIGHTS["chip"]
                + macro_score * RULE_WEIGHTS["macro"]
                + sn * RULE_WEIGHTS["news"]
            )

            rf_prob_up = 0.5
            rf_conf    = 0.0
            if use_rf and rf is not None:
                try:
                    from engine.rf_features import build_feature_vector
                    feat = build_feature_vector(sid)
                    if feat is not None:
                        X      = pd.DataFrame([feat]).fillna(0)
                        X_sc   = sc_model.transform(X)
                        proba  = rf.predict_proba(X_sc)[0]
                        cls    = list(rf.classes_)
                        rf_prob_up = (float(proba[cls.index(1)])
                                      if 1 in cls else 0.5)
                        rf_conf    = float(max(proba))
                except Exception:
                    rf_prob_up = 0.5

            score_total = (
                score_rule * RULE_W_TOTAL
                + rf_prob_up * 100 * RF_W
            )

            price_r = query(f"""
                SELECT close FROM daily_price
                WHERE stock_id='{sid}'
                ORDER BY date DESC LIMIT 1
            """)
            if price_r.empty:
                continue
            close = float(price_r.iloc[0]["close"])

            # 飆股基因計算
            flying_result = compute_flying_stock_score(sid)
            flying_score  = float(
                flying_result.get("flying_score", 0)
            )

            # 第四階段過熱 → 強制降分
            flying_stage = flying_result.get("stage", 0)
            if flying_stage == 4:
                score_total = min(score_total, 45.0)

            flying_all.append(flying_result)

            results.append({
                "stock_id":          sid,
                "score_fundamental": round(sf, 1),
                "score_technical":   round(st, 1),
                "score_chip":        round(sc_score, 1),
                "score_macro":       round(macro_score, 1),
                "score_news":        round(sn, 1),
                "score_rule":        round(score_rule, 1),
                "rf_prob_up":        round(rf_prob_up, 4),
                "rf_confidence":     round(rf_conf, 4),
                "score_total":       round(score_total, 1),
                "flying_score":      round(flying_score, 1),
                "signal":            classify_signal(
                    score_total, st, sc_score, rf_prob_up),
                "target_price":      round(close * 1.12, 1),
                "stop_loss":         round(close * 0.93, 1),
                "optimal_weight":    0.0,
            })

        except Exception as e:
            logging.warning(f"{sid} 計算失敗：{e}")
            continue

        if (i + 1) % 200 == 0:
            logging.info(f"  進度 {i+1}/{len(stocks)}")

    if not results:
        logging.warning("無任何計算結果")
        return {
            "top10":        pd.DataFrame(),
            "top_flying":   [],
            "flying_scan":  [],
            "portfolio":    [],
            "macro_score":  macro_score,
            "market_state": "計算失敗",
            "mode":         mode,
            "days":         readiness["days"],
        }

    score_df = pd.DataFrame(results)
    score_df["date"] = pd.Timestamp.today().strftime("%Y-%m-%d")
    upsert("daily_score", score_df, pk=["stock_id","date"])

    score_df = score_df.sort_values(
        "score_total", ascending=False
    ).reset_index(drop=True)
    top10 = score_df.head(10).copy()

    # 市場狀態
    if macro_score >= 65:   market_state = "牛市"
    elif macro_score <= 40: market_state = "熊市"
    else:                   market_state = "震盪"

    # 飆股結果整理
    flying_map = {r["stock_id"]: r for r in flying_all}

    # 飆股掃描前20（排除第四階段過熱）
    flying_scan = sorted(
        [r for r in flying_all if r["stage"] != 4
         and r["flying_score"] >= 45],
        key=lambda x: x["flying_score"],
        reverse=True
    )[:20]

    # 十大推薦中有飆股訊號的
    top10_ids   = set(top10["stock_id"].tolist())
    top_flying  = [
        r for r in flying_all
        if r["stock_id"] in top10_ids
        and r["flying_score"] >= 45
    ]
    top_flying.sort(key=lambda x: x["flying_score"], reverse=True)

    # 庫存分析（帶飆股資訊）
    portfolio_advice = analyze_portfolio(
        score_df, RULE_W_TOTAL, RF_W, flying_map
    )

    logging.info(
        f"分析完成｜第一名：{top10.iloc[0]['stock_id']} "
        f"（{top10.iloc[0]['score_total']:.1f}分）"
        f"｜飆股掃描：{len(flying_scan)}支"
    )

    return {
        "top10":        top10,
        "top_flying":   top_flying,
        "flying_scan":  flying_scan,
        "flying_map":   flying_map,
        "portfolio":    portfolio_advice,
        "macro_score":  macro_score,
        "market_state": market_state,
        "mode":         mode,
        "days":         readiness["days"],
    }
