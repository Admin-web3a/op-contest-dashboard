#!/usr/bin/env python3
"""
Конкурсный дашборд ОП — Июль 2026
Одна номинация: Капиталист (максимальная выручка).
Считаются все сделки в победных статусах с Датой оплаты 10–31 июля.
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

# Период конкурса (unix timestamp, UTC)
# 10 июля 2026 00:00 Москва = 9 июля 21:00 UTC
CONTEST_START = 1783630800
# 31 июля 2026 23:59:59 Москва = 31 июля 20:59:59 UTC
CONTEST_END   = 1785531599

# Менеджеры
MANAGERS = {
    12377210: "Никита",
    11176694: "Наталья",
     6461602: "Елена",
    11181290: "Сергей",
     9948090: "Денис К.",
    11068965: "Максим",
    10293970: "Влад",
    12738086: "Кирилл",
    11356530: "Денис",
     7728454: "Виктория",
}

# Загружать сделки начиная с 1 июля (с запасом)
UPDATED_FROM = 1782864000  # 2026-07-01

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
        if len(batch) < 250:
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
        cls = ' class="gold"' if i == 0 else (' class="silver"' if i == 1 else (' class="bronze"' if i == 2 else ""))
        html += f'<tr{cls}><td class="rank">{medal}</td><td class="name">{name}</td><td class="metric">{metric}</td><td class="sub">{sub}</td></tr>\n'
    return html


def build_html(stats, updated_at):
    now = datetime.datetime.now(datetime.timezone.utc)
    end_dt = datetime.datetime(2026, 7, 31, 20, 59, 59, tzinfo=datetime.timezone.utc)
    days_left = max(0, (end_dt.date() - now.date()).days)

    cap_rows = sorted(
        [(s["name"], s["revenue"], s["sales"]) for s in stats.values()],
        key=lambda x: -x[1]
    )
    cap_html = leaderboard_rows([
        (name, f"{rev:,} ₽".replace(",", " "), f"{sales} продаж")
        for name, rev, sales in cap_rows
    ])

    updated_str = (datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
                   .strftime("%d.%m.%Y %H:%M МСК"))

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>🏆 Конкурс ОП — Капиталист</title>
<style>
  :root {{
    --gold:   #f5c518;
    --silver: #c0c0c0;
    --bronze: #cd7f32;
    --bg:     #0f0f0f;
    --card:   #1a1a1a;
    --text:   #e8e8e8;
    --sub:    #888;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; }}
  h1 {{ text-align: center; font-size: 1.6rem; margin-bottom: 4px; }}
  .subtitle {{ text-align: center; color: var(--sub); font-size: .85rem; margin-bottom: 24px; }}
  .grid {{ display: grid; grid-template-columns: minmax(300px, 560px); gap: 20px; max-width: 600px; margin: 0 auto; }}
  .card {{ background: var(--card); border-radius: 12px; padding: 20px; }}
  .card h2 {{ font-size: 1.1rem; margin-bottom: 12px; border-bottom: 1px solid #333; padding-bottom: 8px; }}
  .card h2 .desc {{ font-weight: 400; font-size: .8rem; color: var(--sub); display: block; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  td {{ padding: 8px 4px; vertical-align: middle; }}
  .rank  {{ width: 32px; text-align: center; font-size: 1.1rem; }}
  .name  {{ font-weight: 600; }}
  .metric {{ text-align: right; font-weight: 700; font-size: 1.05rem; white-space: nowrap; }}
  .sub   {{ text-align: right; color: var(--sub); font-size: .8rem; white-space: nowrap; padding-left: 8px; }}
  tr.gold   td {{ color: var(--gold); }}
  tr.silver td {{ color: var(--silver); }}
  tr.bronze td {{ color: var(--bronze); }}
  tr + tr {{ border-top: 1px solid #2a2a2a; }}
  .footer {{ text-align: center; color: var(--sub); font-size: .75rem; margin-top: 28px; }}
  .days {{ display: inline-block; background: #222; border-radius: 6px; padding: 2px 8px; margin-left: 6px; font-size: .8rem; }}
</style>
</head>
<body>
<h1>🏆 Конкурс ОП — Капиталист</h1>
<p class="subtitle">10–31 июля · <span class="days">⏳ {days_left} {_days_ru(days_left)} до финала</span></p>

<div class="grid">
  <div class="card">
    <h2>💰 Капиталист <span class="desc">Максимальная выручка</span></h2>
    <table><tbody>
{cap_html}
    </tbody></table>
  </div>
</div>

<p class="footer">Обновлено: {updated_str} · автообновление каждые 5 мин</p>
</body>
</html>"""


def _days_ru(n):
    if n % 10 == 1 and n % 100 != 11:
        return "день"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return "дня"
    return "дней"


# ── Entry point ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Fetching leads from AMO…")
    leads = fetch_all_leads()
    print(f"  Total fetched: {len(leads)}")

    stats = calc_stats(leads)

    won_count = sum(s["sales"] for s in stats.values())
    print(f"  Won in period: {won_count}")

    os.makedirs("docs", exist_ok=True)
    html = build_html(stats, datetime.datetime.utcnow())
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Saved docs/index.html ({len(html):,} bytes)")
