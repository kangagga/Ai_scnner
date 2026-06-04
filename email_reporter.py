# ============================================================
#  email_reporter.py  –  Laporan HTML harian ke Gmail
# ============================================================
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from datetime             import datetime
from config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER

logger = logging.getLogger(__name__)

SIGNAL_COLOR = {
    "STRONG BUY": "#00c853", "BUY": "#4caf50", "WEAK BUY": "#8bc34a",
    "NEUTRAL": "#9e9e9e",
    "WEAK SELL": "#ff9800", "SELL": "#f44336", "STRONG SELL": "#b71c1c",
}


def _badge(signal: str) -> str:
    c = SIGNAL_COLOR.get(signal, "#9e9e9e")
    return (f'<span style="background:{c};color:#fff;padding:2px 8px;'
            f'border-radius:4px;font-size:11px;font-weight:bold;">{signal}</span>')


def _bar(score: int) -> str:
    c = "#00c853" if score >= 90 else "#4caf50" if score >= 85 else "#ff9800"
    return (f'<span style="color:{c};font-family:monospace;">'
            f'{"█"*(int(score)//10)}{"░"*(10-int(score)//10)} {int(score)}</span>')


def build_html(signals: list, ai_analysis: str) -> str:
    now      = datetime.now().strftime("%A, %d %B %Y %H:%M WIB")
    buy_cnt  = sum(1 for s in signals if "BUY"  in s["signal"])
    sell_cnt = sum(1 for s in signals if "SELL" in s["signal"])
    avg_wr   = round(sum(s["win_rate"] for s in signals) / len(signals), 1) if signals else 0

    rows = "".join(f"""
    <tr>
      <td style="padding:6px 10px;border-bottom:1px solid #2a2a2a;font-weight:bold;color:#e0e0e0;">{s['symbol']}</td>
      <td style="padding:6px 10px;border-bottom:1px solid #2a2a2a;color:#90caf9;">{s['timeframe'].upper()}</td>
      <td style="padding:6px 10px;border-bottom:1px solid #2a2a2a;">{_badge(s['signal'])}</td>
      <td style="padding:6px 10px;border-bottom:1px solid #2a2a2a;">{_bar(s['score'])}</td>
      <td style="padding:6px 10px;border-bottom:1px solid #2a2a2a;font-family:monospace;color:#e0e0e0;">{s['entry']}</td>
      <td style="padding:6px 10px;border-bottom:1px solid #2a2a2a;font-family:monospace;color:#ef9a9a;">{s['sl']}</td>
      <td style="padding:6px 10px;border-bottom:1px solid #2a2a2a;font-family:monospace;color:#a5d6a7;">{s['tp2']}</td>
      <td style="padding:6px 10px;border-bottom:1px solid #2a2a2a;color:#fff176;">{s['win_rate']}%</td>
      <td style="padding:6px 10px;border-bottom:1px solid #2a2a2a;color:#ce93d8;">{s['rr_ratio']}</td>
    </tr>""" for s in signals[:50])

    ai_html = (ai_analysis or "Analisa AI tidak tersedia.").replace("\n", "<br>")

    return f"""<!DOCTYPE html><html lang="id">
<head><meta charset="UTF-8">
<style>
  body{{margin:0;padding:0;background:#121212;font-family:Arial,sans-serif;color:#e0e0e0;}}
  .wrap{{max-width:900px;margin:0 auto;padding:20px;}}
  .hdr{{background:linear-gradient(135deg,#0d47a1,#006064);border-radius:12px;
        padding:24px;margin-bottom:20px;text-align:center;}}
  .hdr h1{{margin:0;font-size:22px;color:#fff;letter-spacing:2px;}}
  .hdr p{{margin:6px 0 0;color:#b0bec5;font-size:12px;}}
  .stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px;}}
  .card{{background:#1e1e1e;border:1px solid #333;border-radius:8px;padding:14px;text-align:center;}}
  .card .v{{font-size:26px;font-weight:bold;margin:0;}}
  .card .l{{font-size:11px;color:#888;margin:4px 0 0;}}
  .sec{{background:#1e1e1e;border:1px solid #333;border-radius:8px;padding:16px;margin-bottom:20px;}}
  .sec h2{{margin:0 0 12px;font-size:14px;color:#90caf9;border-bottom:1px solid #333;padding-bottom:8px;}}
  table{{width:100%;border-collapse:collapse;font-size:12px;}}
  th{{background:#263238;color:#90caf9;padding:8px 10px;text-align:left;font-size:11px;}}
  .ai{{background:#0d0d0d;border-left:3px solid #7c4dff;border-radius:0 8px 8px 0;
       padding:16px;line-height:1.8;font-size:13px;}}
  .foot{{text-align:center;color:#555;font-size:11px;margin-top:20px;}}
</style></head>
<body><div class="wrap">
  <div class="hdr">
    <h1>🤖 AI CRYPTO SIGNAL REPORT</h1>
    <p>{now}</p>
    <p style="color:#80cbc4;font-size:11px;">100 Crypto Pairs • TF 1H/4H/Daily • Score ≥85 • Binance • Gemini AI</p>
  </div>
  <div class="stats">
    <div class="card"><p class="v" style="color:#4fc3f7;">{len(signals)}</p><p class="l">Total Sinyal</p></div>
    <div class="card"><p class="v" style="color:#66bb6a;">{buy_cnt}</p><p class="l">BUY</p></div>
    <div class="card"><p class="v" style="color:#ef5350;">{sell_cnt}</p><p class="l">SELL</p></div>
    <div class="card"><p class="v" style="color:#ffd54f;">{avg_wr}%</p><p class="l">Avg Win Rate</p></div>
  </div>
  <div class="sec">
    <h2>🔥 SINYAL TERPILIH (Score ≥85)</h2>
    <table><thead><tr>
      <th>PAIR</th><th>TF</th><th>SIGNAL</th><th>SCORE</th>
      <th>ENTRY</th><th>STOP LOSS</th><th>TP2</th><th>WIN RATE</th><th>R:R</th>
    </tr></thead><tbody>{rows}</tbody></table>
  </div>
  <div class="sec">
    <h2>🧠 ANALISA GEMINI AI</h2>
    <div class="ai">{ai_html}</div>
  </div>
  <div class="foot">
    <p>Dikirim otomatis oleh AI Crypto Signal Bot</p>
    <p>⚠️ Bukan saran investasi. Selalu gunakan manajemen risiko.</p>
  </div>
</div></body></html>"""


def send_email_report(signals: list, ai_analysis: str) -> bool:
    if not EMAIL_SENDER or EMAIL_SENDER == "gmailanda@gmail.com":
        logger.warning("Email belum dikonfigurasi di config.py")
        return False

    now     = datetime.now().strftime("%d %B %Y")
    subject = f"📊 Crypto Signal Report — {now} | {len(signals)} Sinyal Aktif"

    msg = MIMEMultipart("alternative")
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECEIVER
    msg["Subject"] = subject
    msg.attach(MIMEText(build_html(signals, ai_analysis), "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
            srv.login(EMAIL_SENDER, EMAIL_PASSWORD)
            srv.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        logger.info(f"✅ Email terkirim ke {EMAIL_RECEIVER}")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("Gmail auth gagal — pastikan App Password benar")
        return False
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False
