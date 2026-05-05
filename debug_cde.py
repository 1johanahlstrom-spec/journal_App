import os, requests
from dotenv import load_dotenv

base_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(base_dir, '..'))
load_dotenv(os.path.join(parent_dir, '.env'))

headers = {'TZ-API-KEY-ID': os.getenv("TZ_API_KEY"), 'TZ-API-SECRET-KEY': os.getenv("TZ_API_SECRET")}
url = f"https://webapi.tradezero.com/v1/api/accounts/{os.getenv('TZ_ACCOUNT_ID')}/orders-with-pagination/start-date/2026-01-01"
res = requests.get(url, headers=headers, params={'numberOfDays': 365, 'offset': 0, 'limit': 2000})
trades = sorted([t for t in res.json().get('tradingHistory', []) if t['symbol'] == 'CDE'],
                key=lambda t: t['tradeDate'].split('T')[0] + t['execTime'])

for t in trades:
    print(f"{t['tradeDate'].split('T')[0]} {t['execTime']}  {t['side']:12}  qty={t['qty']}  price={t['price']}")