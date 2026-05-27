# engine/report_builder.py
# 每日報告產生器（含深度分析 HTML）
import pandas as pd
from pathlib import Path


def build_deep_report_html(
    top10:            pd.DataFrame,
    deep_results:     list,
    portfolio_advice: list,
    macro_score:      float,
    market_state:     str,
    mode:             str = "full",
    days:             int = 0,
) -> str:

    today = pd.Timestamp.today().strftime("%Y/%m/%d")

    css = """
    <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:Arial,sans-serif;background:#F0F4F8;
         color:#2D3748;line-height:1.6}
    .container{max-width:1100px;margin:0 auto;padding:20px}
    .header{background:linear-gradient(135deg,#1F3864,#2E86C1);
            color:#fff;padding:28px 32px;border-radius:16px;
            margin-bottom:24px}
    .header h1{font-size:24px;margin-bottom:6px}
    .header .meta{font-size:13px;opacity:.8}
    .header .stats{display:flex;gap:16px;
                   margin-top:14px;flex-wrap:wrap}
    .stat{background:rgba(255,255,255,.15);padding:8px 16px;
          border-radius:8px;font-size:13px;text-align:center}
    .stat b{font-size:20px;display:block;margin-bottom:2px}
    .sec-title{font-size:18px;font-weight:600;color:#1F3864;
               border-left:4px solid #2E86C1;padding-left:12px;
               margin:28px 0 16px}
    .top10-grid{display:grid;
                grid-template-columns:repeat(auto-fill,minmax(320px,1fr));
                gap:16px;margin-bottom:24px}
    .scard{background:#fff;border-radius:12px;padding:16px 18px;
           box-shadow:0 2px 8px rgba(0,0,0,.07);
           border-top:4px solid #2E86C1}
    .scard .rank{font-size:12px;color:#888;margin-bottom:4px}
    .scard .sname{font-size:17px;font-weight:600;color:#1F3864;
                  margin-bottom:10px}
    .srow{display:flex;align-items:center;gap:8px;
          margin-bottom:5px;font-size:12px}
    .slbl{width:30px;color:#888}
    .strk{flex:1;height:6px;background:#EEE;
          border-radius:3px;overflow:hidden}
    .sfil{height:6px;border-radius:3px}
    .snum{width:28px;text-align:right;font-weight:600;color:#444}
    .cfoot{display:flex;gap:6px;flex-wrap:wrap;
           margin-top:10px;font-size:12px}
    .tag{padding:3px 8px;border-radius:12px;font-weight:500}
    .tg{background:#E8F8F5;color:#196F3D}
    .tb{background:#EBF5FB;color:#1A5276}
    .tr{background:#FDEDEC;color:#922B21}
    .ty{background:#FEF9E7;color:#7D6608}
    .to{background:#FEF0E7;color:#784212}
    .deep-sec{background:#fff;border-radius:16px;
              padding:24px 28px;margin-bottom:28px;
              box-shadow:0 2px 12px rgba(0,0,0,.07)}
    .dhead{display:flex;align-items:center;gap:12px;
           margin-bottom:20px;padding-bottom:14px;
           border-bottom:1px solid #EEE;flex-wrap:wrap}
    .dbadge{background:#1F3864;color:#fff;padding:6px 14px;
            border-radius:8px;font-size:15px;font-weight:600}
    .dinfo h2{font-size:18px;color:#1F3864}
    .dinfo p{font-size:13px;color:#888;margin-top:2px}
    .dgrid{display:grid;
           grid-template-columns:repeat(auto-fill,minmax(130px,1fr));
           gap:10px;margin-top:14px}
    .ditem{background:#F0F4F8;border-radius:8px;
           padding:10px;text-align:center}
    .dlbl{font-size:11px;color:#888;margin-bottom:4px}
    .dval{font-size:16px;font-weight:600;color:#1F3864}
    .mgrid{display:grid;
           grid-template-columns:repeat(auto-fill,minmax(460px,1fr));
           gap:16px;margin-top:18px}
    .mcard{background:#F8FAFE;border:1px solid #E8EDF5;
           border-radius:10px;padding:16px}
    .mtitle{font-size:13px;font-weight:600;color:#2E86C1;
            margin-bottom:10px}
    .mcontent{font-size:13px;color:#444;
              line-height:1.7;white-space:pre-line}
    .ptable{width:100%;border-collapse:collapse;
            background:#fff;border-radius:12px;overflow:hidden;
            box-shadow:0 2px 8px rgba(0,0,0,.07)}
    .ptable th{background:#1F3864;color:#fff;
               padding:12px 14px;text-align:left;font-size:13px}
    .ptable td{padding:11px 14px;
               border-bottom:1px solid #F0F4F8;font-size:13px}
    .ptable tr:hover{background:#F8FAFE}
    .pp{color:#196F3D;font-weight:600}
    .pn{color:#922B21;font-weight:600}
    .accumulate{background:#fff;border-radius:16px;
                padding:48px 40px;text-align:center;
                box-shadow:0 4px 20px rgba(0,0,0,.08);
                max-width:480px;margin:40px auto}
    .accumulate h2{color:#1F3864;font-size:22px;
                   margin-bottom:12px}
    .progress-wrap{background:#eee;border-radius:8px;
                   height:12px;margin:20px 0}
    .progress-bar{background:#2E86C1;height:12px;border-radius:8px}
    .day-badge{display:inline-block;background:#EBF5FB;
               color:#1A5276;font-size:32px;font-weight:700;
               padding:14px 28px;border-radius:12px;margin:16px 0}
    .footer{text-align:center;color:#AAA;font-size:12px;
            margin-top:32px;padding-bottom:20px}
    @media(max-width:600px){
      .mgrid{grid-template-columns:1fr}
      .top10-grid{grid-template-columns:1fr}
    }
    </style>
    """

    # 資料累積期頁面
    if mode == "accumulating":
        pct = min(int(days / 5 * 100), 100)
        return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="3600">
<title>台股分析系統｜初始化中</title>
{css}
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📊 台股智能分析系統</h1>
    <div class="meta">{today}</div>
  </div>
  <div class="accumulate">
    <h2>系統正在累積歷史資料</h2>
    <p>累積滿 5 個交易日後自動開始推薦</p>
    <div class="day-badge">第 {days} 天 / 5 天</div>
    <div class="progress-wrap">
      <div class="progress-bar" style="width:{pct}%"></div>
    </div>
    <p style="color:#888;font-size:13px">
      資料完整度 {pct}%<br>
      每日 23:30 自動執行，此頁面每小時更新
    </p>
  </div>
</div>
</body>
</html>"""

    # 訊號對照
    sig_tag = {
        "BUY":  ("tg", "✅ BUY"),
        "BUY*": ("tb", "🟩 BUY*"),
        "HOLD": ("tb", "💙 HOLD"),
        "SELL": ("ty", "⚠️ SELL"),
        "CUT":  ("tr", "🚨 CUT"),
    }

    # 十大推薦卡片
    top10_cards = ""
    if not top10.empty:
        for i, (_, row) in enumerate(top10.iterrows()):
            sc, sl = sig_tag.get(
                row.get("signal","HOLD"), ("tb","💙 HOLD")
            )
            bars = ""
            for lbl, key, color in [
                ("基","score_fundamental","#2E86C1"),
                ("技","score_technical",  "#1D9E75"),
                ("籌","score_chip",       "#BA7517"),
            ]:
                val = float(row.get(key, 0) or 0)
                bars += f"""
                <div class="srow">
                  <span class="slbl">{lbl}</span>
                  <div class="strk">
                    <div class="sfil"
                      style="width:{val}%;background:{color}">
                    </div>
                  </div>
                  <span class="snum">{val:.0f}</span>
                </div>"""

            total  = float(row.get("score_total", 0) or 0)
            rf     = float(row.get("rf_prob_up",  0) or 0) * 100
            tgt    = float(row.get("target_price",0) or 0)
            sl_p   = float(row.get("stop_loss",   0) or 0)
            wt     = float(row.get("optimal_weight",0) or 0) * 100

            top10_cards += f"""
            <div class="scard">
              <div class="rank">#{i+1} 推薦</div>
              <div class="sname">
                {row['stock_id']}
                <span style="font-size:13px;color:#888;
                             font-weight:400">
                  &nbsp;總分 {total:.1f}
                </span>
              </div>
              <div>{bars}</div>
              <div class="cfoot">
                <span class="tag {sc}">{sl}</span>
                <span class="tag tb">RF {rf:.0f}%</span>
                <span class="tag tg">目標 {tgt:.1f}</span>
                <span class="tag tr">停損 {sl_p:.1f}</span>
                {f'<span class="tag tb">持倉 {wt:.0f}%</span>'
                 if wt > 0 else ''}
              </div>
            </div>"""

    # 深度分析區塊
    deep_html = ""
    for result in deep_results:
        sid   = result["stock_id"]
        sname = result["stock_name"]
        data  = result.get("data", {})
        mods  = result.get("modules", {})

        fields = [
            ("現價",   f"{data.get('current_price','N/A')} 元"),
            ("PER",    str(data.get('per','N/A'))),
            ("ROE",    f"{data.get('roe','N/A')}%"),
            ("毛利率", f"{data.get('gross_margin','N/A')}%"),
            ("負債率", f"{data.get('debt_ratio','N/A')}%"),
            ("營收YoY",f"{data.get('revenue_yoy','N/A')}%"),
            ("EPS",    str(data.get('eps','N/A'))),
            ("目標價", f"{data.get('target_price','N/A')} 元"),
        ]
        data_items = "".join([
            f"""<div class="ditem">
                  <div class="dlbl">{l}</div>
                  <div class="dval">{v}</div>
                </div>"""
            for l, v in fields
        ])

        module_cards = "".join([
            f"""<div class="mcard">
                  <div class="mtitle">{mod.get('label','')}</div>
                  <div class="mcontent">
                    {mod.get('content','').strip()}
                  </div>
                </div>"""
            for mod in mods.values()
        ])

        score = float(data.get("score_total", 0) or 0)
        rf    = float(data.get("rf_prob_up",  0) or 0) * 100
        sig   = str(data.get("signal", "HOLD"))
        sc, sl = sig_tag.get(sig, ("tb","💙 HOLD"))

        deep_html += f"""
        <div class="deep-sec">
          <div class="dhead">
            <div class="dbadge">{sid}</div>
            <div class="dinfo">
              <h2>{sname}</h2>
              <p>綜合評分 {score:.1f}/100　
                 RF漲機率 {rf:.0f}%</p>
            </div>
            <span class="tag {sc}"
                  style="font-size:14px">{sl}</span>
          </div>
          <div class="dgrid">{data_items}</div>
          <div class="mgrid">{module_cards}</div>
        </div>"""

    # 庫存建議表格
    sig_emoji = {
        "加碼":"🟢","持有":"🔵","觀察":"⚪",
        "減碼":"🟡","出清":"🟠","停損":"🔴",
    }
    port_rows = ""
    total_val = 0
    for p in portfolio_advice:
        pnl = float(p.get("pnl_pct", 0) or 0)
        pc  = "pp" if pnl >= 0 else "pn"
        em  = sig_emoji.get(p.get("signal",""), "▪")
        mv  = int(p.get("market_val", 0) or 0)
        total_val += mv
        port_rows += f"""
        <tr>
          <td><b>{p['stock_id']}</b>&nbsp;{p.get('name','')}</td>
          <td>{float(p.get('cost',0) or 0):.1f}</td>
          <td>{float(p.get('current',0) or 0):.1f}</td>
          <td class="{pc}">{pnl:+.1f}%</td>
          <td>{float(p.get('score',0) or 0):.0f}</td>
          <td>{em}&nbsp;{p.get('signal','')}</td>
          <td style="font-size:12px;color:#555">
            {p.get('action_desc','')}
          </td>
        </tr>"""

    port_section = f"""
    <p style="color:#666;font-size:13px;margin-bottom:12px">
      持倉總市值：
      <b style="color:#1F3864">
        NT${total_val:,}
      </b>
    </p>
    <table class="ptable">
      <tr>
        <th>持倉</th><th>成本</th><th>現價</th>
        <th>損益</th><th>評分</th>
        <th>建議</th><th>操作說明</th>
      </tr>
      {port_rows if port_rows else
       '<tr><td colspan="7" style="text-align:center;'
       'color:#AAA;padding:20px">尚無庫存資料</td></tr>'}
    </table>"""

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>台股日報 {today}</title>
{css}
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📊 台股智能分析深度日報</h1>
    <div class="meta">{today}</div>
    <div class="stats">
      <div class="stat">
        <b>{macro_score:.0f}/100</b>總經分數
      </div>
      <div class="stat">
        <b>{market_state}</b>市場狀態
      </div>
      <div class="stat">
        <b>{len(deep_results)}</b>深度分析
      </div>
      <div class="stat">
        <b>{len(portfolio_advice)}</b>庫存持倉
      </div>
    </div>
  </div>

  <div class="sec-title">🏆 十大買入推薦</div>
  <div class="top10-grid">
    {top10_cards if top10_cards
     else '<p style="color:#AAA;padding:20px">資料累積中</p>'}
  </div>

  <div class="sec-title">🔬 深度研究報告（8大分析模組）</div>
  {deep_html if deep_html
   else '<p style="color:#AAA;padding:20px">資料累積中，'
        '第6天起自動產出</p>'}

  <div class="sec-title">💼 庫存操作建議</div>
  {port_section}

  <div class="footer">
    ⚠️ 本報告由 AI 輔助產出，僅供參考，不構成投資建議。
    台股投資有風險，損益自負。<br>
    每日 23:30 自動更新
  </div>
</div>
</body>
</html>"""


def save_report(html: str) -> None:
    Path("reports").mkdir(exist_ok=True)
    date_str = pd.Timestamp.today().strftime("%Y-%m-%d")
    Path(f"reports/{date_str}.html").write_text(
        html, encoding="utf-8"
    )
    Path("reports/index.html").write_text(
        html, encoding="utf-8"
    )
