#!/usr/bin/env python3
"""
Конкурсный дашборд ОП — Сентябрь 2026.
Одна номинация: Капиталист (максимальная выручка).
Считаются все сделки в победных статусах с Датой оплаты 3–30 сентября.
Без фильтра по рабочему источнику.
Запускается каждые 15 минут через GitHub Actions.
"""

import urllib.request
import json
import os
import datetime

# ── Config ─────────────────────────────────────────────────────────────────────

TOKEN  = os.environ["AMO_TOKEN"]
DOMAIN = "simmihur.amocrm.ru"

# Победные статусы
WON_STATUS_IDS = {142, 78184766}
# 142       = Успешно реализовано
# 78184766  = Внутренняя рассрочка

# Поле «Дата оплаты» (unix timestamp) — основной критерий попадания в конкурс
PAYMENT_DATE_FIELD_ID = 1317071

# Период конкурса по московскому времени
MOSCOW = datetime.timezone(datetime.timedelta(hours=3))
CONTEST_START = int(datetime.datetime(2026, 9, 3, 0, 0, 0, tzinfo=MOSCOW).timestamp())
CONTEST_END = int(datetime.datetime(2026, 9, 30, 23, 59, 59, tzinfo=MOSCOW).timestamp())

# Участники конкурса
MANAGERS = {
    12377210: "Никита",
    11176694: "Наталья",
    11181290: "Сергей",
     6461602: "Елена",
}

# Загружать сделки с небольшим запасом до начала конкурса
UPDATED_FROM = int(datetime.datetime(2026, 9, 1, 0, 0, 0, tzinfo=MOSCOW).timestamp())

# ── AMO helpers ────────────────────────────────────────────────────────────────

def amo_get(path, params=None):
    url = f"https://{DOMAIN}{path}"
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def fetch_all_leads():
    """Fetches all leads in the pipeline updated since UPDATED_FROM."""
    leads = []
    page = 1
    while True:
        data = amo_get("/api/v4/leads", {
            "page": page,
            "limit": 250,
            "filter[pipeline_id]": 9826550,
            "filter[updated_at][from]": UPDATED_FROM,
        })
        batch = data.get("_embedded", {}).get("leads", [])
        if not batch:
            break
        leads.extend(batch)
        if not data.get("_links", {}).get("next"):
            break
        page += 1
    return leads


def get_payment_date(lead):
    """Returns unix timestamp from 'Дата оплаты' field, or 0 if not set."""
    for cf in lead.get("custom_fields_values") or []:
        if cf["field_id"] == PAYMENT_DATE_FIELD_ID:
            vals = cf.get("values") or []
            if vals:
                return int(vals[0].get("value") or 0)
    return 0


def is_won_in_period(lead):
    """Lead is in a won status AND payment date is within the contest period."""
    if lead.get("status_id") not in WON_STATUS_IDS:
        return False
    paid = get_payment_date(lead)
    return CONTEST_START <= paid <= CONTEST_END


# ── Main calculation ────────────────────────────────────────────────────────────

def calc_stats(leads):
    """Returns per-manager stats: {mgr_id: {name, revenue, sales}}"""
    stats = {uid: {"name": name, "revenue": 0, "sales": 0}
             for uid, name in MANAGERS.items()}

    for lead in leads:
        mgr = lead.get("responsible_user_id")
        if mgr not in stats:
            continue
        if not is_won_in_period(lead):
            continue
        stats[mgr]["revenue"] += lead.get("price") or 0
        stats[mgr]["sales"] += 1

    return stats


# ── HTML generation ─────────────────────────────────────────────────────────────

MEDAL = ["🥇", "🥈", "🥉"]


def leaderboard_rows(rows):
    """rows: list of (name, metric_str, sub_str)"""
    html = ""
    for i, (name, metric, sub) in enumerate(rows):
        medal = MEDAL[i] if i < 3 else f"{i+1}."
        cls = " gold" if i == 0 else (" silver" if i == 1 else (" bronze" if i == 2 else ""))
        html += (
            f'<div class="leader-row{cls}">'
            f'<div class="rank">{medal}</div>'
            f'<div class="name">{name}</div>'
            f'<div class="result"><strong>{metric}</strong><span>{sub}</span></div>'
            f'</div>\n'
        )
    return html


def build_html(stats, updated_at):
    now = datetime.datetime.now(MOSCOW)
    end_date = datetime.date(2026, 9, 30)
    days_left = max(0, (end_date - now.date()).days)

    cap_rows = sorted(
        [(s["name"], s["revenue"], s["sales"]) for s in stats.values()],
        key=lambda x: -x[1]
    )
    cap_html = leaderboard_rows([
        (name, f"{rev:,} ₽".replace(",", " "), f"{sales} {_sales_ru(sales)}")
        for name, rev, sales in cap_rows
    ])

    updated_str = now.strftime("%d.%m.%Y %H:%M МСК")

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="300">
<meta name="theme-color" content="#10001f">
<title>🏆 Конкурс ОП — Капиталист</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Unbounded:wght@700;800&display=swap');
  :root {{
    --lime: #d7ff22;
    --violet: #7b16ff;
    --purple: #5010ae;
    --bg: #09000f;
    --card: rgba(54, 7, 105, .72);
    --text: #ffffff;
    --sub: #c9b7dc;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    min-height: 100vh;
    overflow-x: hidden;
    background:
      radial-gradient(circle at 50% -10%, rgba(130, 23, 255, .45), transparent 38rem),
      radial-gradient(circle at 8% 70%, rgba(97, 17, 181, .22), transparent 30rem),
      var(--bg);
    color: var(--text);
    font-family: 'Manrope', sans-serif;
    padding: 28px 18px 32px;
  }}
  body::before {{
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    opacity: .18;
    background-image: linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
                      linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px);
    background-size: 32px 32px;
  }}
  .page {{ position: relative; max-width: 700px; margin: 0 auto; }}
  .brand {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 9px;
    margin-bottom: 24px;
    font-size: .74rem;
    font-weight: 800;
    letter-spacing: .14em;
  }}
  .brand-mark {{
    display: grid;
    place-items: center;
    width: 25px;
    height: 25px;
    border-radius: 7px;
    background: linear-gradient(145deg, #a64aff, #6211dc);
    box-shadow: 0 0 18px rgba(151, 52, 255, .65);
  }}
  .badge {{
    position: relative;
    overflow: hidden;
    text-align: center;
    border: 1px solid rgba(222, 180, 255, .28);
    border-radius: 28px 28px 16px 16px;
    padding: 38px 24px 34px;
    background:
      linear-gradient(145deg, rgba(141, 31, 255, .92), rgba(53, 4, 111, .95)),
      var(--card);
    box-shadow: 0 26px 80px rgba(91, 7, 184, .42), inset 0 1px rgba(255,255,255,.18);
  }}
  .badge::after {{
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: linear-gradient(110deg, transparent 28%, rgba(255,255,255,.12) 40%, transparent 52%);
    transform: translateX(-100%);
    animation: shine 7s ease-in-out infinite;
  }}
  @keyframes shine {{ 0%, 72% {{ transform: translateX(-100%); }} 100% {{ transform: translateX(100%); }} }}
  .money-strip {{
    position: relative;
    height: 84px;
    max-width: 430px;
    margin: 0 auto 24px;
    overflow: hidden;
    border-radius: 15px;
    background: linear-gradient(160deg, #3c076e, #21033e);
    box-shadow: inset 0 8px 25px rgba(0,0,0,.42);
  }}
  .bill {{
    position: absolute;
    display: grid;
    place-items: center;
    width: 43px;
    height: 22px;
    border: 2px solid #1c8f45;
    border-radius: 4px;
    color: #115b2e;
    background: #5ef38c;
    font-size: .67rem;
    font-weight: 800;
    box-shadow: 0 7px 12px rgba(0,0,0,.28);
  }}
  .bill:nth-child(1) {{ left: 7%; top: 19px; transform: rotate(-13deg); }}
  .bill:nth-child(2) {{ left: 27%; top: 45px; transform: rotate(17deg); }}
  .bill:nth-child(3) {{ left: 47%; top: 15px; transform: rotate(8deg); }}
  .bill:nth-child(4) {{ right: 25%; top: 48px; transform: rotate(-18deg); }}
  .bill:nth-child(5) {{ right: 5%; top: 18px; transform: rotate(14deg); }}
  .eyebrow {{ color: var(--lime); font-size: .72rem; font-weight: 800; letter-spacing: .18em; text-transform: uppercase; }}
  h1 {{
    margin: 8px 0 10px;
    color: var(--lime);
    font-family: 'Unbounded', sans-serif;
    font-size: clamp(1.72rem, 6vw, 3rem);
    line-height: 1.05;
    letter-spacing: .015em;
    text-transform: uppercase;
    text-shadow: 0 0 24px rgba(215, 255, 34, .22);
  }}
  .description {{ color: #f2e8fa; font-size: .92rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }}
  .meta {{
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
    margin-top: 24px;
  }}
  .pill {{
    padding: 8px 12px;
    border: 1px solid rgba(255,255,255,.16);
    border-radius: 999px;
    color: #eee2f8;
    background: rgba(17, 0, 36, .36);
    font-size: .78rem;
    font-weight: 600;
  }}
  .pill strong {{ color: white; }}
  .leaderboard {{
    position: relative;
    margin-top: 18px;
    padding: 22px;
    border: 1px solid rgba(189, 115, 255, .24);
    border-radius: 16px 16px 28px 28px;
    background: rgba(24, 2, 45, .86);
    box-shadow: 0 24px 70px rgba(0,0,0,.3);
    backdrop-filter: blur(12px);
  }}
  .section-title {{ margin: 0 2px 16px; font-size: .76rem; font-weight: 800; letter-spacing: .13em; text-transform: uppercase; color: var(--sub); }}
  .leader-row {{
    display: grid;
    grid-template-columns: 46px minmax(0, 1fr) auto;
    align-items: center;
    gap: 10px;
    min-height: 74px;
    padding: 12px 15px;
    border: 1px solid rgba(255,255,255,.07);
    border-radius: 14px;
    background: rgba(255,255,255,.045);
  }}
  .leader-row + .leader-row {{ margin-top: 9px; }}
  .leader-row.gold {{
    border-color: rgba(215, 255, 34, .34);
    background: linear-gradient(90deg, rgba(215,255,34,.14), rgba(255,255,255,.045) 55%);
    box-shadow: 0 0 30px rgba(215,255,34,.07);
  }}
  .leader-row.silver {{ background: linear-gradient(90deg, rgba(218,211,230,.1), rgba(255,255,255,.04) 55%); }}
  .leader-row.bronze {{ background: linear-gradient(90deg, rgba(198,116,65,.12), rgba(255,255,255,.04) 55%); }}
  .rank {{ text-align: center; font-size: 1.35rem; font-weight: 800; }}
  .name {{ min-width: 0; font-size: .98rem; font-weight: 800; }}
  .result {{ text-align: right; }}
  .result strong {{ display: block; color: var(--lime); font-size: 1.06rem; white-space: nowrap; }}
  .result span {{ display: block; margin-top: 2px; color: var(--sub); font-size: .72rem; }}
  .footer {{ text-align: center; color: #8e78a1; font-size: .7rem; margin-top: 20px; }}
  @media (max-width: 520px) {{
    body {{ padding: 16px 10px 24px; }}
    .brand {{ margin-bottom: 15px; }}
    .badge {{ padding: 22px 13px 25px; border-radius: 22px 22px 14px 14px; }}
    .money-strip {{ height: 70px; margin-bottom: 20px; }}
    .leaderboard {{ padding: 12px; margin-top: 10px; border-radius: 14px 14px 22px 22px; }}
    .leader-row {{ grid-template-columns: 36px minmax(0, 1fr) auto; gap: 7px; padding: 11px 9px; }}
    .rank {{ font-size: 1.12rem; }}
    .name {{ font-size: .87rem; }}
    .result strong {{ font-size: .93rem; }}
  }}
</style>
</head>
<body>
<main class="page">
  <div class="brand"><span class="brand-mark">▥</span> WEB3 ACADEMY</div>
  <section class="badge">
    <div class="money-strip" aria-hidden="true">
      <span class="bill">₽</span><span class="bill">₽</span><span class="bill">₽</span><span class="bill">₽</span><span class="bill">₽</span>
    </div>
    <div class="eyebrow">Конкурс отдела продаж</div>
    <h1>Капиталист</h1>
    <p class="description">Побеждает максимальная выручка</p>
    <div class="meta">
      <span class="pill">3–30 сентября</span>
      <span class="pill">Призовой фонд <strong>20 000 ₽</strong></span>
      <span class="pill">⏳ {days_left} {_days_ru(days_left)} до финала</span>
    </div>
  </section>

  <section class="leaderboard">
    <h2 class="section-title">Текущий рейтинг</h2>
{cap_html}
  </section>

  <p class="footer">Обновлено: {updated_str} · данные пересчитываются каждые 15 минут</p>
</main>
</body>
</html>"""


def _days_ru(n):
    if n % 10 == 1 and n % 100 != 11:
        return "день"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return "дня"
    return "дней"


def _sales_ru(n):
    if n % 10 == 1 and n % 100 != 11:
        return "продажа"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return "продажи"
    return "продаж"


# ── Entry point ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Fetching leads from AMO…")
    leads = fetch_all_leads()
    print(f"  Total fetched: {len(leads)}")

    stats = calc_stats(leads)

    won_count = sum(s["sales"] for s in stats.values())
    print(f"  Won in period: {won_count}")

    os.makedirs("docs", exist_ok=True)
    html = build_html(stats, datetime.datetime.now(datetime.timezone.utc))
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Saved docs/index.html ({len(html):,} bytes)")
