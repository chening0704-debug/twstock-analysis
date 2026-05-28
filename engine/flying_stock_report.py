# engine/flying_stock_report.py
# 飆股基因報告產生器
# 產出 HTML 飆股分析區塊，融入每日主報告

import pandas as pd


def build_flying_stock_html(
    flying_results: list,
    top_flying: list,
) -> str:
    """
    產出飆股基因分析 HTML 區塊
    flying_results：全市場飆股掃描結果（前20名）
    top_flying：與十大推薦重疊的飆股結果
    """

    # ── 等級對應樣式 ─────────────────────────────────────────
    grade_style = {
        "強力飆股訊號": ("background:#E8F8F5;color:#085041;"
                        "font-weight:500"),
        "條件成形中":   ("background:#EBF5FB;color:#0C447C;"
                        "font-weight:500"),
        "持續追蹤":     ("background:#FAEEDA;color:#633806;"
                        "font-weight:500"),
        "基因不足":     ("background:#F2F3F4;color:#555555;"
                        "font-weight:400"),
        "⚠️ 過熱警告":  ("background:#FDEDEC;color:#791F1F;"
                        "font-weight:500"),
    }

    stage_style = {
        1: ("background:#E1F5EE;color:#085041", "主力吸籌"),
        2: ("background:#EBF5FB;color:#0C447C", "爆量發動"),
        3: ("background:#FAEEDA;color:#633806", "主升段"),
        4: ("background:#FDEDEC;color:#791F1F", "全民瘋狂"),
        0: ("background:#F2F3F4;color:#555555", "觀察中"),
    }

    # ── 說明區塊 ─────────────────────────────────────────────
    intro_html = """
    <div style="background:#F8FAFE;border:1px solid #E8EDF5;
                border-radius:10px;padding:16px 18px;
                margin-bottom:20px;font-size:13px;
                color:#444;line-height:1.7">
      <b style="color:#1F3864;font-size:14px">
        飆股基因理論說明
      </b><br>
      真正的飆股不是「突然暴漲」，而是「<b>安靜很久→突然甦醒</b>」。
      系統依據5大共同特徵評分（滿分100分）：
      <span style="background:#E1F5EE;color:#085041;padding:1px 6px;
                   border-radius:4px;margin:0 3px">
        橫盤整理20分
      </span>
      <span style="background:#FAEEDA;color:#633806;padding:1px 6px;
                   border-radius:4px;margin:0 3px">
        爆量紅K25分
      </span>
      <span style="background:#EEEDFE;color:#3C3489;padding:1px 6px;
                   border-radius:4px;margin:0 3px">
        MACD翻紅20分
      </span>
      <span style="background:#EBF5FB;color:#0C447C;padding:1px 6px;
                   border-radius:4px;margin:0 3px">
        月線翻揚20分
      </span>
      <span style="background:#FDEDEC;color:#791F1F;padding:1px 6px;
                   border-radius:4px;margin:0 3px">
        突破前高15分
      </span>
      <br>
      <b style="color:#922B21">
        ⚠️ 警告：若系統判定為第四階段「全民瘋狂」，
        代表過熱，切勿追高！
      </b>
    </div>"""

    # ── 與十大推薦重疊的飆股（重點標示）────────────────────
    overlap_html = ""
    if top_flying:
        rows = ""
        for r in top_flying:
            gs = grade_style.get(
                r.get("grade","基因不足"),
                "background:#F2F3F4;color:#555"
            )
            ss, sn = stage_style.get(
                r.get("stage", 0),
                ("background:#F2F3F4;color:#555", "觀察中")
            )
            sub  = r.get("sub_scores", {})
            bars = ""
            color_map = {
                "橫盤整理": ("#1D9E75", 20),
                "爆量紅K":  ("#BA7517", 25),
                "MACD翻紅": ("#7F77DD", 20),
                "月線翻揚": ("#378ADD", 20),
                "突破前高": ("#E24B4A", 15),
            }
            for name, (color, max_s) in color_map.items():
                val     = float(sub.get(name, 0))
                pct     = val / max_s * 100
                bars += f"""
                <div style="display:flex;align-items:center;
                            gap:6px;margin-bottom:3px;
                            font-size:11px">
                  <span style="width:60px;color:#888">
                    {name}
                  </span>
                  <div style="flex:1;height:5px;
                               background:#EEE;border-radius:3px;
                               overflow:hidden">
                    <div style="width:{pct}%;height:5px;
                                 background:{color};
                                 border-radius:3px">
                    </div>
                  </div>
                  <span style="width:24px;text-align:right;
                                font-weight:500;color:#444">
                    {val:.0f}
                  </span>
                </div>"""

            action = r.get("action","")
            rows += f"""
            <tr style="border-bottom:1px solid #F0F4F8">
              <td style="padding:12px 10px;font-weight:600;
                          font-size:14px;color:#1F3864">
                {r['stock_id']}
              </td>
              <td style="padding:12px 10px">
                <span style="font-size:18px;font-weight:600;
                              color:#1F3864">
                  {r['flying_score']:.0f}
                </span>
                <span style="font-size:11px;color:#888">/100</span>
                <div style="margin-top:6px">{bars}</div>
              </td>
              <td style="padding:12px 10px">
                <span style="padding:3px 8px;border-radius:12px;
                              font-size:12px;{gs}">
                  {r.get('grade','')}
                </span>
              </td>
              <td style="padding:12px 10px">
                <span style="padding:3px 8px;border-radius:12px;
                              font-size:12px;{ss}">
                  {r.get('stage_name','')}
                </span>
              </td>
              <td style="padding:12px 10px;font-size:12px;
                          color:#555;line-height:1.5">
                {action}
              </td>
            </tr>"""

        overlap_html = f"""
        <div style="margin-bottom:20px">
          <div style="font-size:14px;font-weight:500;
                      color:#1F3864;margin-bottom:10px">
            十大推薦中的飆股訊號
          </div>
          <table style="width:100%;border-collapse:collapse;
                        background:#fff;border-radius:12px;
                        overflow:hidden;
                        box-shadow:0 2px 8px rgba(0,0,0,.07)">
            <tr style="background:#1F3864;color:#fff">
              <th style="padding:10px;text-align:left;
                          font-size:13px">代號</th>
              <th style="padding:10px;text-align:left;
                          font-size:13px">飆股評分</th>
              <th style="padding:10px;text-align:left;
                          font-size:13px">等級</th>
              <th style="padding:10px;text-align:left;
                          font-size:13px">階段</th>
              <th style="padding:10px;text-align:left;
                          font-size:13px">操作建議</th>
            </tr>
            {rows}
          </table>
        </div>"""

    # ── 全市場飆股掃描前20名 ─────────────────────────────────
    scan_rows = ""
    for r in flying_results[:20]:
        gs = grade_style.get(
            r.get("grade","基因不足"),
            "background:#F2F3F4;color:#555"
        )
        ss, sn = stage_style.get(
            r.get("stage", 0),
            ("background:#F2F3F4;color:#555", "觀察中")
        )
        sub   = r.get("sub_scores", {})
        names = ["橫盤整理","爆量紅K","MACD翻紅","月線翻揚","突破前高"]
        sub_str = " ".join([
            f'<span style="font-size:11px;color:#888">'
            f'{n[:2]}:{float(sub.get(n,0)):.0f}</span>'
            for n in names
        ])
        scan_rows += f"""
        <tr style="border-bottom:1px solid #F0F4F8">
          <td style="padding:9px 10px;font-weight:600;
                      color:#1F3864">{r['stock_id']}</td>
          <td style="padding:9px 10px;font-weight:600;
                      font-size:16px;color:#1F3864">
            {r['flying_score']:.0f}
            <span style="font-size:11px;color:#888;
                          font-weight:400">/100</span>
          </td>
          <td style="padding:9px 10px">
            <span style="padding:2px 7px;border-radius:10px;
                          font-size:12px;{gs}">
              {r.get('grade','')}
            </span>
          </td>
          <td style="padding:9px 10px">
            <span style="padding:2px 7px;border-radius:10px;
                          font-size:12px;{ss}">
              {sn}
            </span>
          </td>
          <td style="padding:9px 10px;font-size:12px;
                      color:#555">{sub_str}</td>
        </tr>"""

    scan_html = f"""
    <div>
      <div style="font-size:14px;font-weight:500;
                  color:#1F3864;margin-bottom:10px">
        全市場飆股基因掃描（前20名）
      </div>
      <table style="width:100%;border-collapse:collapse;
                    background:#fff;border-radius:12px;
                    overflow:hidden;
                    box-shadow:0 2px 8px rgba(0,0,0,.07)">
        <tr style="background:#1F3864;color:#fff">
          <th style="padding:10px;text-align:left;
                      font-size:13px">代號</th>
          <th style="padding:10px;text-align:left;
                      font-size:13px">飆股評分</th>
          <th style="padding:10px;text-align:left;
                      font-size:13px">等級</th>
          <th style="padding:10px;text-align:left;
                      font-size:13px">階段</th>
          <th style="padding:10px;text-align:left;
                      font-size:13px">五項分數</th>
        </tr>
        {scan_rows if scan_rows
         else '<tr><td colspan="5" style="padding:16px;'
              'color:#AAA;text-align:center">'
              '資料累積中</td></tr>'}
      </table>
    </div>"""

    # ── 庫存飆股警示（第四階段過熱） ────────────────────────
    overheated = [
        r for r in flying_results
        if r.get("stage") == 4
    ]
    warning_html = ""
    if overheated:
        items = "".join([
            f'<span style="background:#FDEDEC;color:#791F1F;'
            f'padding:4px 10px;border-radius:8px;'
            f'font-size:13px;font-weight:500;margin:3px">'
            f'{r["stock_id"]} ({r["flying_score"]:.0f}分)'
            f'</span>'
            for r in overheated
        ])
        warning_html = f"""
        <div style="background:#FDEDEC;border-left:4px solid #E24B4A;
                    border-radius:0 10px 10px 0;padding:14px 16px;
                    margin-bottom:20px">
          <div style="font-size:14px;font-weight:500;
                      color:#791F1F;margin-bottom:8px">
            ⚠️ 過熱警告｜以下個股進入第四階段（全民瘋狂）
          </div>
          <div style="font-size:12px;color:#922B21;
                      margin-bottom:8px">
            股價短期漲幅過大，主力可能正在出貨，
            新資金切勿追高，持有者建議分批停利
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:4px">
            {items}
          </div>
        </div>"""

    return f"""
    <div style="margin-bottom:32px">
      {intro_html}
      {warning_html}
      {overlap_html}
      {scan_html}
    </div>"""


def build_flying_stock_email_section(
    top_flying: list,
    overheated_ids: list,
) -> str:
    """產出 Email 版飆股摘要（簡版）"""
    if not top_flying and not overheated_ids:
        return ""

    rows = ""
    grade_color = {
        "強力飆股訊號": "#196F3D",
        "條件成形中":   "#1A5276",
        "持續追蹤":     "#7D6608",
        "⚠️ 過熱警告":  "#922B21",
    }
    for r in top_flying:
        gc = grade_color.get(r.get("grade",""), "#555")
        rows += f"""
        <tr style="border-bottom:1px solid #EEE">
          <td style="padding:8px 10px;font-weight:600">
            {r['stock_id']}
          </td>
          <td style="padding:8px 10px;font-weight:600;
                      color:#1F3864">
            {r['flying_score']:.0f}/100
          </td>
          <td style="padding:8px 10px;color:{gc};
                      font-weight:500">
            {r.get('grade','')}
          </td>
          <td style="padding:8px 10px;font-size:12px;color:#555">
            {r.get('stage_name','')}
          </td>
          <td style="padding:8px 10px;font-size:12px;color:#555">
            {r.get('action','')}
          </td>
        </tr>"""

    warning = ""
    if overheated_ids:
        ids_str = "、".join(overheated_ids)
        warning = f"""
        <div style="background:#FDEDEC;padding:10px 14px;
                    border-radius:8px;font-size:13px;
                    color:#791F1F;margin-top:12px">
          ⚠️ <b>過熱警告</b>：{ids_str} 進入第四階段，
          切勿追高，持有者建議停利
        </div>"""

    return f"""
    <div style="background:#fff;padding:20px 24px;
                margin-bottom:4px">
      <h2 style="color:#1F3864;font-size:16px;
                  margin:0 0 14px">
        🧬 飆股基因分析
      </h2>
      <table style="width:100%;border-collapse:collapse;
                    font-size:13px">
        <tr style="background:#1F3864;color:#fff">
          <th style="padding:8px 10px;text-align:left">代號</th>
          <th style="padding:8px 10px;text-align:left">
            飆股評分
          </th>
          <th style="padding:8px 10px;text-align:left">等級</th>
          <th style="padding:8px 10px;text-align:left">階段</th>
          <th style="padding:8px 10px;text-align:left">
            操作建議
          </th>
        </tr>
        {rows if rows
         else '<tr><td colspan="5" style="padding:12px;'
              'color:#AAA;text-align:center">'
              '資料累積中</td></tr>'}
      </table>
      {warning}
    </div>"""
