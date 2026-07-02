#!/usr/bin/env python3
"""
Конкурсный дашборд ОП — Июль 2026
Три номинации: Капиталист (выручка), Снайпер (конверсия), Охотник (конверсия холодных).
Считаются сделки, закрытые 2–8 июля (Москва), с рабочими источниками запуска 06.26.
Запускается каждые 15 минут через GitHub Actions.
"""

import urllib.request
import json
import os
import datetime

# ── Config ─────────────────────────────────────────────────────────────────────

TOKEN  = os.environ["AMO_TOKEN"]
DOMAIN = "simmihur.amocrm.ru"

# Рабочий источник (select, field 1321741) — 4 допустимых значения
SOURCE_FIELD_ID  = 1321741
SOURCE_ENUM_IDS  = {953633, 954585, 954587, 954645}
# 953633 = Анкета перезаписи 06.2026
# 954585 = Заказ веб 06.26
# 954587 = Предоплата веб 06.26
# 954645 = Присутствовал на вебе 06.26

# Все источники (multiselect, field 1316269) — исключаем для Охотника
ALL_SOURCES_FIELD_ID = 1316269
WEB_ENUM_IDS = {954617, 954723}
# 954617 = Был на вебе 06.26
# 954723 = Был на повторе 06.2026
# (Был на прожарке 06.26 — добавить enum ID после прожарки 02.07)

# Победные статусы
WON_STATUS_IDS = {142, 78184766}
# 142       = Успешно реализовано
# 78184766  = Внутренняя рассрочка

# «Отработанные» — статус ≥ «Взято в работу»
WORKED_STATUS_IDS = {
    78184582,  # Взято в работу
    85544782,  # НДЗ
    78184742,  # Контакт установлен
    78184750,  # Квалифицирован
    85544786,  # Экскурсия
    85544790,  # Встреча с ментором
    78184746,  # Оффер озвучен
    78184758,  # Отложенный спрос
    78184762,  # Выставлен счет
    78184766,  # Внутренняя рассрочка
    142,        # Успешно реализовано
    143,        # Закрыто и не реализовано
}

# Период конкурса (unix timestamp, UTC)
# 2 июля 2026 00:00 Москва = 1 июля 21:00 UTC
CONTEST_START = 1782939600
# 8 июля 2026 23:59:59 Москва = 8 июля 20:59:59 UTC
CONTEST_END   = 1783544399

# Менеджеры (Виолетта и Люба убраны — больше не в команде)
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

# Елена участвует только в «Капиталисте» — в конверсионных номинациях не считается
CONVERSION_EXCLUDED = {6461602}

# Загружать сделки начиная с (не раньше июня)
UPDATED_FROM = 1748736000  # 2026-06-01

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
    """Fetches all leads with eligible source, returns list of lead dicts."""
    leads = []
    page = 1
    while True:
        data = amo_get("/api/v4/leads", {
            "page": page,
            "limit": 250,
            "filter[pipeline_id]": 9826550,
            "filter[updated_at][from]": UPDATED_FROM,
            "with": "contacts",
        })
        batch = data.get("_embedded", {}).get("leads", [])
        if not batch:
            break
        leads.extend(batch)
        if len(batch) < 250:
            break
        page += 1
    return leads


def get_field_value(lead, field_id):
    """Returns list of enum IDs for a custom field on a lead."""
    for cf in lead.get("custom_fields_values") or []:
        if cf["field_id"] == field_id:
            return [v["enum_id"] for v in (cf.get("values") or []) if v.get("enum_id")]
    return []


def is_eligible(lead):
    """Lead must have one of the 4 working sources."""
    source_enums = get_field_value(lead, SOURCE_FIELD_ID)
    return bool(set(source_enums) & SOURCE_ENUM_IDS)


def is_cold(lead):
    """Lead has not attended the webinar, replay, or probiarka."""
    all_sources = set(get_field_value(lead, ALL_SOURCES_FIELD_ID))
    return not bool(all_sources & WEB_ENUM_IDS)


def is_won_in_period(lead):
    """Lead is won AND closed within contest period."""
    if lead.get("status_id") not in WON_STATUS_IDS:
        return False
    closed = lead.get("closed_at") or 0
    return CONTEST_START <= closed <= CONTEST_END


def is_worked(lead):
    """Lead is in 'Взято в работу' or higher (denominator for conversion)."""
    return lead.get("status_id") in WORKED_STATUS_IDS


# ── Main calculation ────────────────────────────────────────────────────────────

def calc_stats(leads):
    """
    Returns per-manager stats:
    {mgr_id: {revenue, won, worked, cold_won, cold_worked, name}}
    """
    stats = {}
    for uid, name in MANAGERS.items():
        stats[uid] = {
            "name": name,
            "revenue": 0,    # Капиталист
            "won": 0,        # Снайпер numerator
            "worked": 0,     # Снайпер denominator
            "cold_won": 0,   # Охотник numerator
            "cold_worked": 0 # Охотник denominator
        }

    for lead in leads:
        if not is_eligible(lead):
            continue
        mgr = lead.get("responsible_user_id")
        if mgr not in stats:
            continue

        cold = is_cold(lead)
        won  = is_won_in_period(lead)
        worked = is_worked(lead)
        in_conversion = mgr not in CONVERSION_EXCLUDED

        if worked and in_conversion:
            stats[mgr]["worked"] += 1
            if cold:
                stats[mgr]["cold_worked"] += 1

        if won:
            stats[mgr]["revenue"] += lead.get("price") or 0
            if in_conversion:
                stats[mgr]["won"] += 1
                if cold:
                    stats[mgr]["cold_won"] += 1

    return stats


# ── HTML generation ─────────────────────────────────────────────────────────────

MEDAL = ["🥇", "🥈", "🥉"]

def pct(num, denom):
    if denom == 0:
        return 0.0
    return round(num / denom * 100, 1)


def leaderboard_rows(rows):
    """rows: list of (rank0, name, metric_str, sub_str)"""
    html = ""
    for i, (name, metric, sub) in enumerate(rows):
        medal = MEDAL[i] if i < 3 else f"{i+1}."
        gold_class = ' class="gold"' if i == 0 else (' class="silver"' if i == 1 else (' class="bronze"' if i == 2 else ""))
        html += f'<tr{gold_class}><td class="rank">{medal}</td><td class="name">{name}</td><td class="metric">{metric}</td><td class="sub">{sub}</td></tr>\n'
    return html


def build_html(stats, updated_at):
    now = datetime.datetime.utcnow()
    start_dt = datetime.datetime(2026, 7, 2, tzinfo=datetime.timezone.utc)
    end_dt   = datetime.datetime(2026, 7, 8, 23, 59, 59, tzinfo=datetime.timezone.utc)
    days_left = max(0, (end_dt.date() - now.date()).days)

    # ── Капиталист ── (включает всех, кто получил хотя бы одну продажу)
    cap_rows = sorted(
        [(s["name"], s["revenue"], s["won"]) for s in stats.values()],
        key=lambda x: -x[1]
    )
    cap_html = leaderboard_rows([
        (name, f"{rev:,} ₽".replace(",", " "), f"{won} продаж")
        for name, rev, won in cap_rows
    ])

    # ── Снайпер ──
    sniper_rows = sorted(
        [(s["name"], pct(s["won"], s["worked"]), s["won"], s["worked"])
         for s in stats.values() if s["worked"] > 0],
        key=lambda x: (-x[1], -x[2])
    )
    sniper_html = leaderboard_rows([
        (name, f"{p}%", f"{won} из {worked}")
        for name, p, won, worked in sniper_rows
    ])

    # ── Охотник ──
    hunter_rows = sorted(
        [(s["name"], pct(s["cold_won"], s["cold_worked"]), s["cold_won"], s["cold_worked"])
         for s in stats.values() if s["cold_worked"] > 0],
        key=lambda x: (-x[1], -x[2])
    )
    hunter_html = leaderboard_rows([
        (name, f"{p}%", f"{won} из {worked} холодных")
        for name, p, won, worked in hunter_rows
    ])

    updated_str = (datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
                   .strftime("%d.%m.%Y %H:%M МСК"))

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>🏆 Конкурс ОП — Июль 2026</title>
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
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; max-width: 1100px; margin: 0 auto; }}
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
<h1>🏆 Конкурс ОП — Июль 2026</h1>
<p class="subtitle">2–8 июля · Призовой фонд 60 000 ₽ · <span class="days">⏳ {days_left} {_days_ru(days_left)} до финала</span></p>

<div class="grid">

  <div class="card">
    <h2>💰 Капиталист <span class="desc">Максимальная выручка</span></h2>
    <table><tbody>
{cap_html}
    </tbody></table>
  </div>

  <div class="card">
    <h2>🎯 Снайпер <span class="desc">Лучшая общая конверсия</span></h2>
    <table><tbody>
{sniper_html}
    </tbody></table>
  </div>

  <div class="card">
    <h2>🦅 Охотник <span class="desc">Конверсия по холодной базе</span></h2>
    <table><tbody>
{hunter_html}
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

    eligible_count = sum(1 for l in leads if is_eligible(l))
    won_count = sum(s["won"] for s in stats.values())
    print(f"  Eligible: {eligible_count} | Won in period: {won_count}")

    os.makedirs("docs", exist_ok=True)
    html = build_html(stats, datetime.datetime.utcnow())
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Saved docs/index.html ({len(html):,} bytes)")
