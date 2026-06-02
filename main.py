# main.py — GitHub Actions 主入口 v6
# 整合：飆股基因 + 進階技術 + 產業鏈 + 自我學習引擎
import os
import sys
import logging
import datetime
import pandas as pd
from pathlib import Path

Path("logs").mkdir(exist_ok=True)
Path("data").mkdir(exist_ok=True)
Path("models").mkdir(exist_ok=True)
Path("reports").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("logs/analysis.log"),
        logging.StreamHandler(sys.stdout),
    ]
)


def main():
    logging.info("=" * 55)
    logging.info(
        "台股智能分析系統 v6.0 啟動"
        "（飆股基因 + 自我學習 + 產業鏈）"
    )

    # ── Step 1：初始化 SQLite ─────────────────────────────────
    from db import init_db
    init_db()
    logging.info("SQLite 初始化完成")

    # ── Step 2：台灣時區開市判斷 ──────────────────────────────
    tw_tz    = datetime.timezone(datetime.timedelta(hours=8))
    now_tw   = datetime.datetime.now(tw_tz)
    today_tw = now_tw.date()
    weekday  = today_tw.weekday()
    wd_name  = ["一","二","三","四","五","六","日"][weekday]

    logging.info(
        f"台灣現在時間：{now_tw.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    logging.info(f"今天星期{wd_name}")

    if weekday >= 5:
        logging.info(f"今日週{wd_name}，系統不執行")
        Path("reports/skip.txt").write_text(
            f"{today_tw} 週末休市"
        )
        sys.exit(0)

    from market_calendar import MarketCalendarGuard
    guard = MarketCalendarGuard()
    if not guard.is_trading_day(today_tw):
        logging.info(f"今日 {today_tw} 國定假日，系統不執行")
        Path("reports/skip.txt").write_text(
            f"{today_tw} 國定假日休市"
        )
        sys.exit(0)

    logging.info(f"今日 {today_tw} 台股開市，開始執行")

    # ── Step 3：讀取 Excel 庫存 ───────────────────────────────
    from portfolio_excel import (
        load_portfolio_from_excel,
        write_results_to_excel,
    )
    n = load_portfolio_from_excel()
    logging.info(f"庫存載入：{n} 支持倉")

    # ── Step 4：七路並行資料擷取 ──────────────────────────────
    from concurrent.futures import ThreadPoolExecutor
    from collectors import (
        collect_price_volume,
        collect_institutional,
        collect_margin,
        collect_chip_broker,
        collect_financials,
        collect_macro,
        collect_announcements,
    )

    with ThreadPoolExecutor(max_workers=4) as ex:
        tasks = {
            "price_volume":  ex.submit(collect_price_volume),
            "institutional": ex.submit(collect_institutional),
            "margin":        ex.submit(collect_margin),
            "chip_broker":   ex.submit(collect_chip_broker),
            "financials":    ex.submit(collect_financials),
            "macro":         ex.submit(collect_macro),
            "announcements": ex.submit(collect_announcements),
        }
        counts = {}
        for name, f in tasks.items():
            try:
                counts[name] = f.result()
                logging.info(
                    f"  [{name}] 完成 {counts[name]} 筆"
                )
            except Exception as e:
                logging.error(f"  [{name}] 失敗：{e}")
                counts[name] = 0

    # ── Step 5：確認 price_volume 有資料 ──────────────────────
    if counts.get("price_volume", 0) == 0:
        from db import query
        check = query(
            "SELECT COUNT(*) as cnt "
            "FROM daily_price WHERE volume>0"
        )
        total = int(check["cnt"].iloc[0]) \
                if not check.empty else 0
        if total == 0:
            logging.error(
                "DB 完全無資料，"
                "TWSE 資料可能尚未更新，中止分析"
            )
            sys.exit(1)
        logging.warning(
            f"今日資料未更新，"
            f"使用 DB 現有 {total} 筆資料繼續"
        )

    # ── Step 6：主分析引擎（含所有新模組）────────────────────
    logging.info(
        "啟動主分析引擎 v6"
        "（五維 + 飆股基因 + 進階技術 + 產業鏈 + 自我學習）"
    )
    from engine.scorer import run_analysis_engine
    results = run_analysis_engine()

    mode         = results.get("mode", "")
    days         = results.get("days", 0)
    top_flying   = results.get("top_flying",   [])
    flying_scan  = results.get("flying_scan",  [])
    learning     = results.get("learning",     {})
    intl_linkage = results.get("intl_linkage", {})
    adapt_weights= results.get("adapt_weights",{})

    # 過熱警告
    overheated_ids = [
        r["stock_id"] for r in flying_scan
        if r.get("stage") == 4
    ]
    if overheated_ids:
        logging.warning(
            f"⚠️ 過熱警告：{', '.join(overheated_ids)}"
        )

    # ── Step 7：深度分析（Gemini 8大模組）────────────────────
    deep_results = []
    if mode == "full" and not results["top10"].empty:
        logging.info(
            "執行十大推薦深度分析"
            "（8大模組 + Gemini AI）..."
        )
        try:
            from engine.deep_analysis import (
                run_deep_analysis_top10
            )
            deep_results = run_deep_analysis_top10(
                results["top10"]
            )
            logging.info(
                f"深度分析完成：{len(deep_results)} 支"
            )
        except Exception as e:
            logging.error(f"深度分析失敗：{e}")

    # ── Step 8：產出完整報告 HTML ─────────────────────────────
    from engine.report_builder import (
        build_deep_report_html,
        save_report,
    )
    html = build_deep_report_html(
        top10            = results.get(
            "top10", pd.DataFrame()),
        deep_results     = deep_results,
        portfolio_advice = results.get("portfolio",    []),
        macro_score      = results.get("macro_score",  50),
        market_state     = results.get("market_state", "—"),
        mode             = mode,
        days             = days,
        top_flying       = top_flying,
        flying_scan      = flying_scan,
        learning         = learning,
        intl_linkage     = intl_linkage,
        adapt_weights    = adapt_weights,
    )
    save_report(html)
    logging.info("HTML 報告已產出")

    # ── Step 9：資料累積期 ────────────────────────────────────
    if mode == "accumulating":
        logging.info(
            f"資料累積期（第 {days} 天），發進度通知"
        )
        _send_accumulating_email(days)
        sys.exit(0)

    # ── Step 10：回寫 Excel 庫存 ──────────────────────────────
    write_results_to_excel(results["portfolio"])

    # ── Step 11：推送完整報告 ────────────────────────────────
    from notifier import send_report
    send_report(results, html)

    # ── Step 12：統計摘要 ─────────────────────────────────────
    strong_flying  = [
        r for r in flying_scan
        if r.get("flying_score", 0) >= 75
    ]
    bt = learning.get("backtest", {})
    logging.info(
        f"\n{'='*55}\n"
        f"  今日分析摘要\n"
        f"{'='*55}\n"
        f"  市場狀態：{results.get('market_state','—')}\n"
        f"  總經分數：{results.get('macro_score',0):.0f}/100\n"
        f"  AI情緒：{intl_linkage.get('ai_sentiment','—')}\n"
        f"  強力飆股訊號：{len(strong_flying)} 支\n"
        f"  過熱警告：{len(overheated_ids)} 支\n"
        f"  昨日推薦勝率："
        f"{bt.get('win_rate',0):.0%} "
        f"（{bt.get('hits',0)}/{bt.get('total',0)}）\n"
        f"  當前自適應權重：\n"
        + "\n".join([
            f"    {k}：{v*100:.1f}%"
            for k, v in adapt_weights.items()
        ])
        + f"\n{'='*55}"
    )

    logging.info("全部完成！v6.0")
    logging.info("=" * 55)


def _send_accumulating_email(days: int):
    import os, smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    eu = os.environ.get("EMAIL_USER",   "")
    ep = os.environ.get("EMAIL_PASS",   "")
    et = os.environ.get("EMAIL_TARGET", "")
    if not eu or not ep or not et:
        return

    pct   = min(int(days / 5 * 100), 100)
    today = datetime.date.today().strftime("%Y/%m/%d")

    html = f"""
<div style="font-family:Arial;max-width:520px;
            margin:0 auto;padding:24px;background:#f5f7fa">
  <div style="background:linear-gradient(135deg,#1F3864,#2E86C1);
              color:#fff;padding:24px;
              border-radius:12px 12px 0 0;text-align:center">
    <h2 style="margin:0;font-size:20px">
      📊 台股分析系統 v6｜資料累積中
    </h2>
    <p style="margin:6px 0 0;opacity:.8;font-size:13px">
      {today}
    </p>
  </div>
  <div style="background:#fff;padding:28px 24px;
              border-radius:0 0 12px 12px;text-align:center">
    <p style="color:#555;font-size:15px;margin-bottom:16px">
      系統正在累積歷史資料，進度如下：
    </p>
    <div style="font-size:48px;font-weight:700;
                color:#1A5276;margin:8px 0">
      第 {days} 天 / 5 天
    </div>
    <div style="background:#eee;border-radius:8px;
                height:14px;margin:16px 20px">
      <div style="background:#2E86C1;height:14px;
                  border-radius:8px;width:{pct}%"></div>
    </div>
    <p style="color:#888;font-size:13px;
              margin-bottom:20px">
      資料完整度 {pct}%
    </p>
    <div style="display:grid;grid-template-columns:1fr 1fr;
                gap:10px;text-align:left">
      <div style="background:#E1F5EE;border-radius:8px;
                  padding:12px;font-size:12px;color:#085041">
        🧬 <b>飆股基因模組</b><br>
        第 6 天起自動掃描全市場飆股訊號
      </div>
      <div style="background:#EBF5FB;border-radius:8px;
                  padding:12px;font-size:12px;color:#1A5276">
        🧠 <b>自我學習引擎</b><br>
        每日驗證推薦結果，自動調整權重
      </div>
      <div style="background:#EEEDFE;border-radius:8px;
                  padding:12px;font-size:12px;color:#3C3489">
        🏭 <b>產業鏈分析</b><br>
        AI算力/半導體等產業鏈連動追蹤
      </div>
      <div style="background:#FAEEDA;border-radius:8px;
                  padding:12px;font-size:12px;color:#633806">
        📊 <b>8大深度分析</b><br>
        Gemini AI 自動產出研究報告
      </div>
    </div>
    <p style="color:#AAA;font-size:12px;margin-top:20px">
      明日繼續累積，請耐心等待 🙏<br>
      每晚 23:30 自動執行
    </p>
  </div>
</div>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"📊 台股系統 v6 累積進度 "
            f"第{days}天/5天 {today}"
        )
        msg["From"] = eu
        msg["To"]   = et
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(eu, ep)
            s.send_message(msg)
        logging.info("[accumulating] 進度通知信已發送")
    except Exception as e:
        logging.warning(f"[accumulating] 通知信失敗：{e}")


if __name__ == "__main__":
    main()
