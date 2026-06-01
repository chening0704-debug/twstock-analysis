# engine/self_learning.py
# 自我調適學習引擎
# 功能：
#   1. 每日推薦後自動回測次日結果
#   2. 依準確率以貝葉斯更新各維度權重
#   3. 弱訊號自動降權、強訊號自動升權
#   4. 每週產出系統自我診斷報告

import json
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import date, timedelta
from db import query, upsert

WEIGHTS_PATH  = Path("models/adaptive_weights.json")
HISTORY_PATH  = Path("models/prediction_history.json")
DIAGNOSIS_PATH= Path("reports/diagnosis.json")

# 各維度預設權重
DEFAULT_WEIGHTS = {
    "fundamental": 0.35,
    "technical":   0.25,
    "chip":        0.25,
    "macro":       0.10,
    "news":        0.05,
    "flying":      0.00,   # 飆股基因初始權重
    "advanced":    0.00,   # 進階技術初始權重
}

# 權重邊界（避免單一維度過大或過小）
WEIGHT_BOUNDS = {
    "fundamental": (0.15, 0.50),
    "technical":   (0.10, 0.40),
    "chip":        (0.10, 0.40),
    "macro":       (0.05, 0.20),
    "news":        (0.02, 0.15),
    "flying":      (0.00, 0.20),
    "advanced":    (0.00, 0.15),
}

# 學習率（控制每次更新幅度）
LEARNING_RATE = 0.03


class SelfLearningEngine:

    def __init__(self):
        self.weights = self._load_weights()
        self.history = self._load_history()

    def _load_weights(self) -> dict:
        if WEIGHTS_PATH.exists():
            try:
                w = json.loads(WEIGHTS_PATH.read_text())
                # 確保所有維度都存在
                for k, v in DEFAULT_WEIGHTS.items():
                    if k not in w:
                        w[k] = v
                return w
            except Exception:
                pass
        return DEFAULT_WEIGHTS.copy()

    def _load_history(self) -> list:
        if HISTORY_PATH.exists():
            try:
                return json.loads(HISTORY_PATH.read_text())
            except Exception:
                pass
        return []

    def _save_weights(self):
        WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        WEIGHTS_PATH.write_text(
            json.dumps(self.weights, indent=2)
        )

    def _save_history(self):
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        # 保留最近 180 筆
        self.history = self.history[-180:]
        HISTORY_PATH.write_text(
            json.dumps(self.history, indent=2)
        )

    # ──────────────────────────────────────────────────────────
    # Step 1：記錄今日推薦（供次日回測用）
    # ──────────────────────────────────────────────────────────
    def record_predictions(self, top10: pd.DataFrame):
        """
        記錄今日十大推薦的各維度分數與進場價
        次日執行時自動比對實際漲跌
        """
        if top10.empty:
            return

        today = date.today().isoformat()
        records = []
        for _, row in top10.iterrows():
            records.append({
                "date":          today,
                "stock_id":      row["stock_id"],
                "score_total":   float(row.get("score_total",   0) or 0),
                "score_f":       float(row.get("score_fundamental",0) or 0),
                "score_t":       float(row.get("score_technical",  0) or 0),
                "score_c":       float(row.get("score_chip",       0) or 0),
                "score_m":       float(row.get("score_macro",      0) or 0),
                "score_n":       float(row.get("score_news",       0) or 0),
                "flying_score":  float(row.get("flying_score",     0) or 0),
                "rf_prob_up":    float(row.get("rf_prob_up",       0) or 0),
                "entry_price":   float(row.get("target_price", 0) * 0.94 or 0),
                "signal":        str(row.get("signal", "HOLD")),
                "actual_chg":    None,   # 次日填入
                "hit":           None,   # 次日填入
            })

        self.history.extend(records)
        self._save_history()
        logging.info(
            f"[SelfLearning] 記錄 {len(records)} 筆今日預測"
        )

    # ──────────────────────────────────────────────────────────
    # Step 2：次日自動回測（填入實際漲跌）
    # ──────────────────────────────────────────────────────────
    def backtest_yesterday(self) -> dict:
        """
        取昨日推薦，比對今日收盤，計算準確率
        命中定義：BUY 訊號後次日漲幅 > 0（正報酬）
        """
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        # 週一回測週五的預測
        if date.today().weekday() == 0:
            yesterday = (date.today() - timedelta(days=3)).isoformat()

        pending = [
            r for r in self.history
            if r["date"] == yesterday and r["actual_chg"] is None
        ]

        if not pending:
            logging.info("[SelfLearning] 無待回測記錄")
            return {}

        results  = {"date": yesterday, "total": 0, "hits": 0,
                    "details": []}
        updated  = 0

        for rec in pending:
            sid = rec["stock_id"]
            try:
                prices = query(f"""
                    SELECT close FROM daily_price
                    WHERE stock_id = '{sid}'
                    AND date >= '{yesterday}'
                    AND volume > 0
                    ORDER BY date LIMIT 2
                """)
                if len(prices) < 2:
                    continue

                entry_price = float(prices["close"].iloc[0])
                exit_price  = float(prices["close"].iloc[1])
                actual_chg  = (exit_price - entry_price) / (entry_price + 1e-9) * 100
                hit         = actual_chg > 0

                # 更新歷史記錄
                for r in self.history:
                    if (r["date"] == yesterday
                            and r["stock_id"] == sid
                            and r["actual_chg"] is None):
                        r["actual_chg"] = round(actual_chg, 4)
                        r["hit"]        = hit
                        break

                results["total"] += 1
                if hit:
                    results["hits"] += 1
                results["details"].append({
                    "stock_id":   sid,
                    "actual_chg": round(actual_chg, 2),
                    "hit":        hit,
                    "signal":     rec["signal"],
                    "score_total":rec["score_total"],
                })
                updated += 1

            except Exception as e:
                logging.warning(
                    f"[SelfLearning] {sid} 回測失敗：{e}"
                )

        self._save_history()
        results["win_rate"] = (
            results["hits"] / results["total"]
            if results["total"] > 0 else 0
        )
        logging.info(
            f"[SelfLearning] 回測完成："
            f"勝率={results['win_rate']:.1%} "
            f"（{results['hits']}/{results['total']}）"
        )
        return results

    # ──────────────────────────────────────────────────────────
    # Step 3：貝葉斯權重更新
    # ──────────────────────────────────────────────────────────
    def update_weights_bayesian(self, lookback: int = 20):
        """
        貝葉斯更新各維度權重：
        計算每個維度分數與實際漲跌的相關係數
        相關性高的維度 → 增加權重
        相關性低的維度 → 減少權重
        """
        completed = [
            r for r in self.history
            if r.get("actual_chg") is not None
        ][-lookback:]

        if len(completed) < 10:
            logging.info(
                "[SelfLearning] 歷史資料不足10筆，跳過權重更新"
            )
            return

        df = pd.DataFrame(completed)
        actual = df["actual_chg"].values.astype(float)

        dims = {
            "fundamental": "score_f",
            "technical":   "score_t",
            "chip":        "score_c",
            "macro":       "score_m",
            "news":        "score_n",
            "flying":      "flying_score",
        }

        correlations = {}
        for dim, col in dims.items():
            if col in df.columns:
                scores = df[col].values.astype(float)
                if np.std(scores) > 0:
                    corr = float(np.corrcoef(scores, actual)[0, 1])
                    correlations[dim] = corr if not np.isnan(corr) else 0
                else:
                    correlations[dim] = 0

        logging.info(f"[SelfLearning] 各維度相關係數：{correlations}")

        # 貝葉斯更新：相關性高則升權，低則降權
        new_weights = self.weights.copy()
        for dim, corr in correlations.items():
            if dim not in new_weights:
                continue
            old_w = new_weights[dim]
            # 相關性轉換為調整方向（正相關升權，負相關降權）
            adjustment = LEARNING_RATE * corr
            new_w = old_w + adjustment
            # 套用邊界限制
            lo, hi = WEIGHT_BOUNDS.get(dim, (0.02, 0.50))
            new_weights[dim] = round(
                float(np.clip(new_w, lo, hi)), 4
            )

        # 正規化（確保總和為1）
        total = sum(new_weights.values())
        if total > 0:
            new_weights = {
                k: round(v/total, 4)
                for k, v in new_weights.items()
            }

        logging.info(
            f"[SelfLearning] 權重更新：{self.weights} "
            f"→ {new_weights}"
        )
        self.weights = new_weights
        self._save_weights()

    # ──────────────────────────────────────────────────────────
    # Step 4：系統自我診斷報告
    # ──────────────────────────────────────────────────────────
    def generate_diagnosis(self) -> dict:
        """
        每週產出系統自我診斷報告
        分析各維度貢獻度、準確率趨勢、建議調整方向
        """
        completed = [
            r for r in self.history
            if r.get("actual_chg") is not None
        ]

        if len(completed) < 5:
            return {"status": "資料不足，請累積更多預測紀錄"}

        df = pd.DataFrame(completed)

        # 整體統計
        total     = len(df)
        win_rate  = float(df["hit"].mean())
        avg_ret   = float(df["actual_chg"].mean())
        best_ret  = float(df["actual_chg"].max())
        worst_ret = float(df["actual_chg"].min())

        # 近7日趨勢
        recent = df.tail(min(7, len(df)))
        recent_win = float(recent["hit"].mean())

        # 各訊號統計
        signal_stats = {}
        for sig in ["BUY", "BUY*", "HOLD"]:
            sig_df = df[df["signal"] == sig]
            if len(sig_df) > 0:
                signal_stats[sig] = {
                    "count":    int(len(sig_df)),
                    "win_rate": round(float(sig_df["hit"].mean()), 4),
                    "avg_ret":  round(float(sig_df["actual_chg"].mean()), 4),
                }

        # 維度重要性排名（依相關係數）
        dims = {
            "基本面": "score_f",
            "技術面": "score_t",
            "籌碼面": "score_c",
            "總經面": "score_m",
            "飆股基因":"flying_score",
        }
        dim_importance = {}
        actual = df["actual_chg"].values.astype(float)
        for name, col in dims.items():
            if col in df.columns and len(df[col].dropna()) >= 5:
                scores = df[col].values.astype(float)
                if np.std(scores) > 0:
                    corr = float(
                        np.corrcoef(scores, actual)[0, 1]
                    )
                    dim_importance[name] = round(corr, 4) \
                        if not np.isnan(corr) else 0

        dim_importance = dict(
            sorted(dim_importance.items(),
                   key=lambda x: abs(x[1]), reverse=True)
        )

        # 建議
        suggestions = []
        if recent_win < 0.45:
            suggestions.append(
                "近7日勝率偏低，系統已自動觸發參數重估"
            )
        if win_rate > 0.60:
            suggestions.append(
                "整體勝率良好，維持現有策略"
            )
        if avg_ret > 0:
            suggestions.append(
                f"平均報酬率 {avg_ret:+.2f}%，策略有效"
            )

        best_dim = max(dim_importance.items(),
                       key=lambda x: x[1]) \
                   if dim_importance else ("N/A", 0)
        suggestions.append(
            f"最有預測力的維度：{best_dim[0]}"
            f"（相關係數 {best_dim[1]:.3f}）"
        )

        diagnosis = {
            "generated_at":   date.today().isoformat(),
            "total_records":  total,
            "win_rate":       round(win_rate, 4),
            "recent_win_rate":round(recent_win, 4),
            "avg_return":     round(avg_ret, 4),
            "best_return":    round(best_ret, 4),
            "worst_return":   round(worst_ret, 4),
            "signal_stats":   signal_stats,
            "dim_importance": dim_importance,
            "current_weights":self.weights,
            "suggestions":    suggestions,
        }

        DIAGNOSIS_PATH.parent.mkdir(parents=True, exist_ok=True)
        DIAGNOSIS_PATH.write_text(
            json.dumps(diagnosis, indent=2, ensure_ascii=False)
        )
        logging.info("[SelfLearning] 診斷報告已產出")
        return diagnosis

    # ──────────────────────────────────────────────────────────
    # 主執行函數
    # ──────────────────────────────────────────────────────────
    def run_daily(self, top10: pd.DataFrame) -> dict:
        """
        每日執行完整自我學習流程：
        1. 回測昨日預測
        2. 更新權重
        3. 記錄今日預測
        4. 週日產出診斷報告
        """
        logging.info("[SelfLearning] 開始自我學習流程")

        # Step 1：回測昨日
        backtest_result = self.backtest_yesterday()

        # Step 2：更新權重（有足夠資料才更新）
        self.update_weights_bayesian(lookback=20)

        # Step 3：記錄今日預測
        self.record_predictions(top10)

        # Step 4：週日產出診斷報告
        diagnosis = {}
        if date.today().weekday() == 6:
            diagnosis = self.generate_diagnosis()
            logging.info("[SelfLearning] 週日診斷報告已產出")

        logging.info(
            f"[SelfLearning] 完成｜"
            f"當前權重：{self.weights}"
        )

        return {
            "backtest":  backtest_result,
            "weights":   self.weights,
            "diagnosis": diagnosis,
        }

    def get_current_weights(self) -> dict:
        """取得當前自適應權重"""
        return self.weights.copy()


def get_adaptive_weights() -> dict:
    """供 scorer.py 呼叫的便捷函數"""
    engine = SelfLearningEngine()
    return engine.get_current_weights()
