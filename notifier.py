# notifier.py — Email 報告推送（完整版）
import os
import smtplib
import logging
import pandas as pd
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

EMAIL_USER   = os.environ.get("EMAIL_USER",   "")
EMAIL_PASS   = os.environ.get("EMAIL_PASS",   "")
EMAIL_TARGET = os.environ.get("EMAIL_TARGET", "")

SIGNAL_EMOJI = {
    "BUY":  "✅", "BUY*": "🟩",
    "HOLD": "💙", "SELL": "⚠️", "CUT": "🚨",
    "加碼": "🟢", "持有": "🔵", "觀察": "⚪",
    "減碼": "🟡", "出清": "🟠", "停損": "🔴",
}


def generate_html_email(
    results: dict,
    html_content: str = None
) -> str:
    """
    若有完整深度報告 HTML 直接使用
    否則產出簡版 Email 格式
    """
    if html_content:
        return html_content

    top10  = results.get("top10", pd.DataFrame())
    port   = results.get("portfolio", [])
    macro  = results.get("macro_score", 50)
    state  = results.get("market_state", "—")
    today  = pd.Timestamp.today().strftime("%Y/%m/%d")

    # 十大推薦列
    rows_top10 = ""
    if not top10.empty:
        for i, (_, row) in enumerate(top10.iterrows()):
            sig   = str(row.get("signal", "HOLD"))
            emoji = SIGNAL_EMOJI.get(sig, "")
            color = "#196F3D" if "BUY" in sig else "#555"
            rows_top10 += f"""
            <tr style="border-bottom:1px solid #eee">
              <td style="padding:8px 10px;font-weight:600">
                {i+1}. {row['stock_id']}
              </td>
              <td style="padding:8px 10px">
                {float(row.get('score_total',0) or 0):.1f}
              </td>
              <td style="padding:8px 10px">
                基{float(row.get('score_fundamental',0) or 0):.0f}
                技{float(row.get('score_technical',0) or 0):.0f}
                籌{float(row.get('score_chip',0) or 0):.0f}
              </td>
              <td style="padding:8px 10px">
                {float(row.get('rf_prob_up',0) or 0)*100:.0f}%
              </td>
              <td style="padding:8px 10px;
                         color:{color};font-weight:600">
                {emoji} {sig}
              </td>
              <td style="padding:8px 10px">
                目標 {float(row.get('target_price',0) or 0):.1f}
                <br>
                <span style="color:#922B21">
                  停損 {float(row.get('stop_loss',0) or 0):.1f}
                </span>
              </td>
            </tr>"""

    # 庫存建議列
    rows_port = ""
    total_val = 0
    for p in port:
        pnl = float(p.get("pnl_pct", 0) or 0)
        mv  = int(p.get("market_val", 0) or 0)
        total_val += mv
        pc    = "#196F3D" if pnl >= 0 else "#922B21"
        sig   = p.get("signal", "觀察")
        emoji = SIGNAL_EMOJI.get(sig, "▪")
        sc    = "#196F3D" if sig in ["加碼","持有"] else "#922B21"
        rows_port += f"""
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:8px 10px;font-weight:600">
            {p['stock_id']}<br>
            <span style="font-weight:400;font-size:12px;
                         color:#888">
              {p.get('name','')}
            </span>
          </td>
          <td style="padding:8px 10px">
            {float(p.get('cost',0) or 0):.1f}
          </td>
          <td style="padding:8px 10px">
            {float(p.get('current',0) or 0):.1f}
          </td>
          <td style="padding:8px 10px;
                     color:{pc};font-weight:600">
            {pnl:+.1f}%
          </td>
          <td style="padding:8px 10px">
            {float(p.get('score',0) or 0):.0f}分
          </td>
          <td style="padding:8px 10px;
                     color:{sc};font-weight:600">
            {emoji} {sig}
          </td>
          <td style="padding:8px 10px;font-size:12px;
                     color:#555">
            {p.get('action_desc','')}
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="font-family:Arial,sans-serif;max-width:900px;
             margin:0 auto;padding:20px;background:#f5f5f5">

  <div style="background:#1F3864;color:#fff;
              padding:20px 24px;
              border-radius:10px 10px 0 0">
    <h1 style="margin:0;font-size:20px">
      📊 台股智能分析深度日報
    </h1>
    <p style="margin:6px 0 0;font-size:13px;opacity:.8">
      {today}
    </p>
  </div>

  <div style="background:#fff;padding:16px 24px;
              border-bottom:1px solid #eee">
    <span style="margin-right:20px;font-size:13px">
      🌐 總經分數：<b>{macro:.0f}/100</b>
    </span>
    <span style="font-size:13px">
      📈 市場狀態：<b>{state}</b>
    </span>
  </div>

  <div style="background:#fff;padding:20px 24px;
              margin-bottom:4px">
    <h2 style="color:#1F3864;font-size:16px;
               margin:0 0 14px">
      🏆 十大買入推薦
    </h2>
    <table style="width:100%;border-collapse:collapse;
                  font-size:13px">
      <tr style="background:#1F3864;color:#fff">
        <th style="padding:8px 10px;text-align:left">代號</th>
        <th style="padding:8px 10px;text-align:left">總分</th>
        <th style="padding:8px 10px;text-align:left">五維</th>
        <th style="padding:8px 10px;text-align:left">
          RF漲機率
        </th>
        <th style="padding:8px 10px;text-align:left">訊號</th>
        <th style="padding:8px 10px;text-align:left">價位</th>
      </tr>
      {rows_top10 if rows_top10 else
       '<tr><td colspan="6" style="padding:16px;'
       'color:#AAA;text-align:center">'
       '資料累積中</td></tr>'}
    </table>
  </div>

  <div style="background:#fff;padding:20px 24px">
    <h2 style="color:#1F3864;font-size:16px;
               margin:0 0 6px">
      💼 庫存操作建議
    </h2>
    <p style="font-size:13px;color:#666;margin-bottom:14px">
      持倉總市值：
      <b style="color:#1F3864">NT${total_val:,}</b>
    </p>
    <table style="width:100%;border-collapse:collapse;
                  font-size:13px">
      <tr style="background:#1F3864;color:#fff">
        <th style="padding:8px 10px;text-align:left">持倉</th>
        <th style="padding:8px 10px;text-align:left">成本</th>
        <th style="padding:8px 10px;text-align:left">現價</th>
        <th style="padding:8px 10px;text-align:left">損益</th>
        <th style="padding:8px 10px;text-align:left">評分</th>
        <th style="padding:8px 10px;text-align:left">建議</th>
        <th style="padding:8px 10px;text-align:left">說明</th>
      </tr>
      {rows_port if rows_port else
       '<tr><td colspan="7" style="padding:16px;'
       'color:#AAA;text-align:center">'
       '尚無庫存資料</td></tr>'}
    </table>
  </div>

  <div style="background:#EBF5FB;padding:14px 24px;
              border-radius:0 0 10px 10px;
              font-size:12px;color:#555;text-align:center">
    🔬 完整深度研究報告（8大分析模組）請查看網頁版：<br>
    <a href="https://chening0704-debug.github.io/twstock-analysis/"
       style="color:#2E86C1;font-weight:600">
      chening0704-debug.github.io/twstock-analysis/
    </a>
  </div>

  <div style="background:#f0f0f0;padding:12px 24px;
              margin-top:4px;
              font-size:11px;color:#888;text-align:center">
    ⚠️ 本報告由 AI 輔助產出，僅供參考，
    不構成投資建議。台股投資有風險，損益自負。
  </div>

</body>
</html>"""


def send_email(
    results: dict,
    html_content: str = None
) -> bool:
    if not EMAIL_USER or not EMAIL_PASS or not EMAIL_TARGET:
        logging.warning("[notifier] Email 設定不完整，跳過")
        return False

    today   = pd.Timestamp.today().strftime("%m/%d")
    subject = f"📊 台股深度日報 {today}"
    html    = generate_html_email(results, html_content)

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = EMAIL_USER
        msg["To"]      = EMAIL_TARGET
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(EMAIL_USER, EMAIL_PASS)
            s.send_message(msg)

        logging.info(
            f"[notifier] Email 發送成功 → {EMAIL_TARGET}"
        )
        return True

    except Exception as e:
        logging.error(f"[notifier] Email 發送失敗：{e}")
        return False


def send_report(
    results: dict,
    html_content: str = None
):
    """主推送入口"""
    send_email(results, html_content)

    try:
        Path("reports").mkdir(exist_ok=True)
        date_str = pd.Timestamp.today().strftime("%Y-%m-%d")
        if html_content:
            Path(f"reports/{date_str}.html").write_text(
                html_content, encoding="utf-8"
            )
            Path("reports/index.html").write_text(
                html_content, encoding="utf-8"
            )
        logging.info("[notifier] HTML 報告已儲存")
    except Exception as e:
        logging.error(f"[notifier] HTML 儲存失敗：{e}")
