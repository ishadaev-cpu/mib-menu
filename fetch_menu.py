"""Забирает из Saby меню дня столовой МИБ 3 и пишет docs/menu.json.
Ключи берутся из переменных окружения SABY_APP_ID, SABY_APP_SECRET, SABY_SECRET_KEY (секреты GitHub)."""
import os, re, json, time, datetime as dt, urllib.request, urllib.parse

POINT = 5511                      # МИБ 3
ANCHOR = dt.date(2026, 11, 2)     # понедельник недели Н1 (цикл Н1 → Н2 → Н3)
WDN = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
MSK = dt.timezone(dt.timedelta(hours=3))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'docs', 'menu.json')


def retry(f):
    def w(*a, **k):
        for i in range(5):
            try:
                return f(*a, **k)
            except Exception:
                if i == 4:
                    raise
                time.sleep(3 + 3 * i)
    return w


# ключи из секретов GitHub; убираем случайные пробелы, переносы и кавычки при вставке
KEY = {k: os.environ.get(k, '').strip().strip('`"\' ').strip() for k in ('SABY_APP_ID', 'SABY_APP_SECRET', 'SABY_SECRET_KEY')}
print('длины ключей:', {k: len(v) for k, v in KEY.items()}, '(должно быть 16, 24, 118)')


@retry
def auth():
    body = json.dumps({"app_client_id": KEY['SABY_APP_ID'], "app_secret": KEY['SABY_APP_SECRET'],
                       "secret_key": KEY['SABY_SECRET_KEY']}).encode()
    r = urllib.request.urlopen(urllib.request.Request('https://online.sbis.ru/oauth/service/', data=body,
                               headers={'Content-Type': 'application/json; charset=utf-8'}), timeout=60)
    j = json.loads(r.read())
    return j['token'], j['sid']


TOK = auth()


@retry
def get(path, **q):
    u = 'https://api.sbis.ru/retail/' + path + '?' + urllib.parse.urlencode(q)
    req = urllib.request.Request(u, headers={'X-SBISAccessToken': TOK[0], 'X-SBISSessionID': TOK[1]})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def week_no(d):
    mon = d - dt.timedelta(days=d.weekday())
    return ((mon - ANCHOR).days // 7) % 3 + 1


def main():
    now = dt.datetime.now(MSK)
    day = now.date()
    lists = get('nomenclature/price-list', pointId=POINT, actualDate=now.strftime('%Y-%m-%d %H:%M:%S'), pageSize=100)['priceLists']
    # ручная замена: docs/override.json вида {"2026-11-05": "Н2 четверг нов"}
    ov_path = os.path.join(os.path.dirname(OUT), 'override.json')
    override = json.load(open(ov_path, encoding='utf-8')).get(day.isoformat()) if os.path.exists(ov_path) else None
    want_w, want_d = week_no(day), WDN[day.weekday()]
    chosen = None
    for pl in lists:
        if override and pl['name'].strip().lower() == override.strip().lower():
            chosen = pl; break
        m = re.match(r'\s*Н\s*(\d)\s+(\w+)', pl['name'], re.I)
        if not override and m and int(m.group(1)) == want_w and m.group(2).lower() == want_d:
            chosen = pl; break
    if not chosen:
        print('нет прайса на', day, want_w, want_d); return
    noms = get('nomenclature/list', pointId=POINT, priceListId=chosen['id'], withBalance='true', pageSize=500)['nomenclatures']
    folders = {n['hierarchicalId']: n['name'].strip() for n in noms if n.get('isParent')}
    menu = {}
    for n in noms:
        if n.get('isParent') or n.get('cost') is None:
            continue
        f = folders.get(n.get('hierarchicalParent'), '(корень)')
        f = {'выпечка': 'Выпечка'}.get(f.lower(), f)
        menu.setdefault(f, []).append({'name': n['name'].strip(), 'price': n['cost'],
                                       'desc': (n.get('description_simple') or '').strip()})
    data = {'source': {'list': chosen['name'].strip(), 'date': day.isoformat()}, 'menu': menu}
    old = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else None
    if old and old.get('menu') == menu and old['source'] == data['source']:
        print('без изменений:', chosen['name']); return
    data['updated'] = now.strftime('%Y-%m-%d %H:%M')
    json.dump(data, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('обновлено:', chosen['name'], sum(len(v) for v in menu.values()), 'позиций')


main()
