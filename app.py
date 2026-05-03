import os, math, json
from datetime import datetime, timedelta
from pathlib import Path

import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from dotenv import load_dotenv

# --- SETUP ---
base_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(base_dir, '..'))
load_dotenv(os.path.join(parent_dir, '.env'))

def get_secret(key):
    try: return st.secrets[key]
    except: return os.getenv(key)

API_KEY    = get_secret("TZ_API_KEY")
API_SECRET = get_secret("TZ_API_SECRET")
ACCOUNT_ID = get_secret("TZ_ACCOUNT_ID")
BASE_URL   = "https://webapi.tradezero.com/v1/api"

SIDE_MAP = {
    'BUY':'BUY','B':'BUY','BOT':'BUY','COVER':'BUY','BUYTOCOVER':'BUY','C':'BUY',
    'SELL':'SELL','S':'SELL','SLD':'SELL','SHORT':'SELL','SS':'SELL','SELLSHORT':'SELL',
}
STRATEGIES = ["–", "Breakout / Flag", "Episodic Pivot", "Parabolic Short"]
GRADES     = ["–", "A", "B", "C", "F"]
ANNOTATIONS_FILE = os.path.join(base_dir, "annotations.json")

# --- PAGE ---
st.set_page_config(page_title="Trading Journal", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;700;800&display=swap');
:root{--bg:#0a0a0f;--surface:#111118;--border:#1e1e2e;--accent:#00ff88;--accent2:#ff3366;--text:#e8e8f0;--muted:#555570;--card:#13131c;}
html,body,.stApp{background-color:var(--bg)!important;color:var(--text)!important;font-family:'Syne',sans-serif;}
.stApp>header{background:transparent!important;}
[data-testid="stSidebar"]{display:none!important;}
[data-testid="collapsedControl"]{display:none!important;}
#MainMenu,footer,header{visibility:hidden;}
.block-container{padding:2rem!important;max-width:1100px!important;margin:0 auto!important;}
.metric-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.2rem;text-align:center;}
.metric-card:hover{border-color:var(--accent);}
.metric-label{font-family:'Space Mono',monospace;font-size:0.85rem;letter-spacing:0.15em;color:#9999aa;text-transform:uppercase;margin-bottom:0.4rem;}
.metric-value{font-family:'Space Mono',monospace;font-size:1.5rem;font-weight:700;line-height:1.1;}
.metric-sub{font-family:'Space Mono',monospace;font-size:0.75rem;color:#ffffff;margin-top:0.2rem;}
.positive{color:#00ff88;}.negative{color:#ff3366;}.neutral{color:var(--text);}
.app-header{display:flex;align-items:baseline;gap:1rem;margin-bottom:2rem;border-bottom:1px solid var(--border);padding-bottom:1.5rem;}
.app-title{font-family:'Syne',sans-serif;font-weight:800;font-size:2.5rem;color:var(--text);letter-spacing:-0.02em;}
.app-subtitle{font-family:'Space Mono',monospace;font-size:0.9rem;color:#9999aa;letter-spacing:0.1em;}
.section-header{font-family:'Space Mono',monospace;font-size:0.95rem;letter-spacing:0.2em;color:#9999aa;text-transform:uppercase;margin:1.5rem 0 1rem 0;padding-bottom:0.5rem;border-bottom:1px solid var(--border);}
.live-dot{display:inline-block;width:8px;height:8px;background:var(--accent);border-radius:50%;margin-right:6px;animation:pulse 1.5s infinite;}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:0.4;transform:scale(0.8)}}
.stButton>button{background:transparent!important;border:1px solid var(--accent)!important;color:var(--accent)!important;font-family:'Space Mono',monospace!important;font-size:0.75rem!important;letter-spacing:0.1em!important;border-radius:6px!important;}
.stButton>button:hover{background:var(--accent)!important;color:var(--bg)!important;}
.stTabs [data-baseweb="tab-list"]{background:transparent!important;border-bottom:1px solid var(--border)!important;}
.stTabs [data-baseweb="tab"]{background:transparent!important;color:#9999aa!important;font-family:'Space Mono',monospace!important;font-size:0.9rem!important;letter-spacing:0.1em!important;border:none!important;}
.stTabs [aria-selected="true"]{color:var(--accent)!important;border-bottom:2px solid var(--accent)!important;}
</style>
""", unsafe_allow_html=True)


# --- ANNOTATIONS ---
def load_annotations():
    if 'annotations' not in st.session_state:
        try:
            if os.path.exists(ANNOTATIONS_FILE):
                with open(ANNOTATIONS_FILE, 'r', encoding='utf-8') as f:
                    st.session_state.annotations = json.load(f)
            else:
                st.session_state.annotations = {}
        except Exception as e:
            st.session_state.annotations = {}
    # Migrate old grade format to new
    grade_map = {"A — Jättebra": "A", "B — Bra": "B", "C — Dålig": "C"}
    for v in st.session_state.annotations.values():
        if v.get('grade', '–') in grade_map:
            v['grade'] = grade_map[v['grade']]
    return st.session_state.annotations

def save_annotations():
    try:
        with open(ANNOTATIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(st.session_state.annotations, f, indent=2, ensure_ascii=False)
        return True
    except:
        return False

def trade_key(row):
    return f"{row['Ticker']}|{row['Datum']}|{row.get('Entry Datum','')}"


# --- API ---
@st.cache_data(ttl=300, show_spinner=False)
def fetch_all_trades():
    h = {'TZ-API-KEY-ID': API_KEY, 'TZ-API-SECRET-KEY': API_SECRET}
    all_trades, offset = [], 0
    try:
        while True:
            url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/orders-with-pagination/start-date/2026-01-01"
            res = requests.get(url, headers=h, params={'numberOfDays':365,'offset':offset,'limit':100}, timeout=10)
            data = res.json()
            batch = data.get('tradingHistory', [])
            if not batch: break
            all_trades.extend(batch)
            if len(all_trades) >= data.get('pagination',{}).get('totalRecords',0): break
            offset += 100
        return all_trades
    except Exception as e:
        st.error(f"API-fel: {e}"); return []

@st.cache_data(ttl=30, show_spinner=False)
def fetch_pnl():
    h = {'TZ-API-KEY-ID': API_KEY, 'TZ-API-SECRET-KEY': API_SECRET}
    try:
        res = requests.get(f"{BASE_URL}/accounts/{ACCOUNT_ID}/pnl", headers=h, timeout=10)
        return res.json()
    except: return {}

@st.cache_data(ttl=30, show_spinner=False)
def fetch_positions():
    h = {'TZ-API-KEY-ID': API_KEY, 'TZ-API-SECRET-KEY': API_SECRET}
    try:
        res = requests.get(f"{BASE_URL}/accounts/{ACCOUNT_ID}/positions", headers=h, timeout=10)
        return res.json().get('positions', [])
    except: return []

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_chart_data(ticker, start_date, end_date):
    try:
        import yfinance as yf
        start = (pd.to_datetime(start_date) - timedelta(days=45)).strftime('%Y-%m-%d')
        end   = (pd.to_datetime(end_date)   + timedelta(days=10)).strftime('%Y-%m-%d')
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if df.empty:
            # Try with common suffixes for different exchanges
            for suffix in ['.ST', '.L', '.TO']:
                df = yf.download(ticker + suffix, start=start, end=end, progress=False, auto_adjust=True)
                if not df.empty: break
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        return df
    except Exception as e:
        return str(e)

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_news(tickers):
    try:
        import yfinance as yf
        all_news = []
        for ticker in tickers:
            try:
                t = yf.Ticker(ticker)
                news = t.news
                if news:
                    for item in news[:3]:
                        content = item.get('content', {})
                        title = content.get('title', '')
                        provider = content.get('provider', {}).get('displayName', '')
                        pub_date = content.get('pubDate', '')
                        url = content.get('canonicalUrl', {}).get('url', '')
                        if not url:
                            url = content.get('clickThroughUrl', {}).get('url', '')
                        if title:
                            all_news.append({
                                'ticker': ticker,
                                'title': title,
                                'provider': provider,
                                'date': pub_date[:10] if pub_date else '',
                                'url': url,
                            })
            except: pass
        return all_news
    except: return []


# --- FIFO ENGINE ---
def compute_fifo(all_trades):
    rows = []
    for t in all_trades:
        side = SIDE_MAP.get(str(t.get('side','')).strip().upper())
        if not side: continue
        trade_date = (t.get('tradeDate') or '').split('T')[0]
        exec_time  = t.get('execTime') or '00:00:00'
        rows.append({
            'Symbol': t.get('symbol'), 'Side': side,
            'Antal': float(t.get('qty') or 0), 'Pris': float(t.get('price') or 0),
            'Tidsstämpel': pd.to_datetime(f"{trade_date}T{exec_time}", errors='coerce'),
            'Datum': trade_date,
            'Courtage': float(t.get('totalFees') or 0) + float(t.get('commission') or 0),
        })
    df = pd.DataFrame(rows).sort_values('Tidsstämpel').reset_index(drop=True)
    valid_trades = []

    for symbol, group in df.groupby('Symbol'):
        long_fifo, short_fifo, position = [], [], 0.0
        entry_time, entry_date = None, None

        for _, row in group.iterrows():
            qty, price, side = abs(float(row['Antal'])), abs(float(row['Pris'])), row['Side']
            ts, datum = row['Tidsstämpel'], row['Datum']
            courtage = float(row['Courtage'])
            if math.isnan(price) or qty == 0 or price == 0: continue

            # Set entry time when opening from flat
            if abs(position) < 0.01 and qty > 0:
                entry_time, entry_date = ts, datum

            if side == 'BUY':
                if position < -0.01:
                    # Closing short (fully or partially)
                    close_qty = min(qty, abs(position))  # only close what we have
                    remaining, pnl, cost = close_qty, 0.0, 0.0
                    while remaining > 0.01 and short_fifo:
                        oq, op = short_fifo[0]; m = min(remaining, oq)
                        pnl += m*(op-price); cost += m*op
                        remaining -= m; oq -= m
                        if oq < 0.01: short_fifo.pop(0)
                        else: short_fifo[0] = (oq, op)
                    if cost > 0:
                        pct = (pnl/cost*100)
                        dur = round((ts - entry_time).total_seconds()/60) if entry_time else None
                        valid_trades.append({'Ticker':symbol, 'Vinst ($)':round(pnl,2), 'Vinst %':round(pct,1),
                            'Riktning':'SHORT', 'Datum':datum, 'Entry Datum':entry_date or datum,
                            'Tidsstämpel':ts, 'Hålltid (min)':dur, 'Courtage':courtage})
                    # Position flip: buy more than short position → open long
                    flip_qty = qty - close_qty
                    new_position = position + qty
                    if abs(new_position) < 0.01:
                        entry_time = entry_date = None  # fully closed
                    elif new_position > 0.01 and position < -0.01:
                        # Flipped to long
                        entry_time, entry_date = ts, datum
                        long_fifo.append((flip_qty, price))
                else:
                    # Opening/adding to long
                    if abs(position) < 0.01: entry_time, entry_date = ts, datum
                    long_fifo.append((qty, price))
                position += qty

            else:  # SELL
                if position > 0.01:
                    # Closing long (fully or partially)
                    close_qty = min(qty, position)
                    remaining, pnl, cost = close_qty, 0.0, 0.0
                    while remaining > 0.01 and long_fifo:
                        oq, op = long_fifo[0]; m = min(remaining, oq)
                        pnl += m*(price-op); cost += m*op
                        remaining -= m; oq -= m
                        if oq < 0.01: long_fifo.pop(0)
                        else: long_fifo[0] = (oq, op)
                    if cost > 0:
                        pct = (pnl/cost*100)
                        dur = round((ts - entry_time).total_seconds()/60) if entry_time else None
                        valid_trades.append({'Ticker':symbol, 'Vinst ($)':round(pnl,2), 'Vinst %':round(pct,1),
                            'Riktning':'LONG', 'Datum':datum, 'Entry Datum':entry_date or datum,
                            'Tidsstämpel':ts, 'Hålltid (min)':dur, 'Courtage':courtage})
                    # Position flip: sell more than long position → open short
                    flip_qty = qty - close_qty
                    new_position = position - qty
                    if abs(new_position) < 0.01:
                        entry_time = entry_date = None
                    elif new_position < -0.01 and position > 0.01:
                        entry_time, entry_date = ts, datum
                        short_fifo.append((flip_qty, price))
                else:
                    if abs(position) < 0.01: entry_time, entry_date = ts, datum
                    short_fifo.append((qty, price))
                position -= qty
    return pd.DataFrame(valid_trades)


# --- HELPERS ---
def fmt_duration(minutes):
    if minutes is None or (isinstance(minutes, float) and math.isnan(minutes)): return "–"
    minutes = int(minutes)
    if minutes < 60: return f"{minutes}m"
    if minutes < 1440:
        h, m = divmod(minutes, 60)
        return f"{h}h {m}m" if m else f"{h}h"
    days = minutes // 1440; h = (minutes % 1440) // 60
    return f"{days}d {h}h" if h else f"{days}d"

PLOTLY_LAYOUT = dict(
    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
    font=dict(family='Space Mono', color='#888899', size=11),
    xaxis=dict(gridcolor='#1e1e2e', linecolor='#1e1e2e'),
    yaxis=dict(gridcolor='#1e1e2e', linecolor='#1e1e2e'),
    margin=dict(l=10, r=10, t=30, b=10),
)

def mcard(label, value, fmt="dollar", sub=None):
    if fmt == "dollar":   val_str = f"${value:+,.0f}"
    elif fmt == "pct":    val_str = f"{value:+.0f}%"
    elif fmt == "int":    val_str = str(int(value))
    elif fmt == "x":      val_str = f"{value:.2f}x"
    elif fmt == "time":   val_str = fmt_duration(value)
    else:                 val_str = str(value)
    cls = "positive" if (isinstance(value,(int,float)) and value>0) else "negative" if (isinstance(value,(int,float)) and value<0) else "neutral"
    sub_part = f'<div class="metric-sub">{sub}</div>' if sub else ""
    return f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value {cls}">{val_str}</div>{sub_part}</div>'


# --- HEADER ---
st.markdown("""<div class="app-header"><span class="app-title">TRADING JOURNAL</span><span class="app-subtitle">// TRADEZERO ACCOUNT ANALYTICS</span></div>""", unsafe_allow_html=True)

# --- CONTROLS (top bar instead of sidebar) ---
ctrl_col1, ctrl_col2 = st.columns([3, 1])
with ctrl_col1:
    with st.expander("⚙ FILTER & INSTÄLLNINGAR", expanded=False):
        fc1, fc2, fc3, fc4, fc5 = st.columns(5)
        with fc1:
            date_from = st.date_input("Från datum", value=datetime(2026, 1, 1))
        with fc2:
            date_to = st.date_input("Till datum", value=datetime.today())
        with fc3:
            show_long  = st.checkbox("LONG",  value=True)
            show_short = st.checkbox("SHORT", value=True)
        with fc4:
            strat_filter = st.selectbox("Strategi", ["Alla"] + STRATEGIES[1:])
        with fc5:
            ann = load_annotations()
            tagged_count = sum(1 for v in ann.values() if v.get('strategy','–') != '–' or v.get('grade','–') != '–')
            st.caption(f"{tagged_count} taggade trades")
            if st.session_state.get('annotations'):
                st.download_button("⬇ EXPORTERA",
                    data=json.dumps(st.session_state.annotations, indent=2, ensure_ascii=False),
                    file_name="annotations.json", mime="application/json")
            uploaded = st.file_uploader("⬆ IMPORTERA", type="json", label_visibility="collapsed")
            if uploaded:
                try:
                    imported = json.loads(uploaded.read().decode('utf-8'))
                    st.session_state.annotations = imported
                    save_annotations()
                    st.success(f"Importerade {len(imported)} anteckningar")
                    st.rerun()
                except:
                    st.error("Ogiltig JSON-fil")
with ctrl_col2:
    if st.button("↻  UPPDATERA DATA"):
        st.cache_data.clear(); st.rerun()


# --- LOAD ---
annotations = load_annotations()
with st.spinner("Hämtar data..."):
    all_trades = fetch_all_trades()
    pnl_data   = fetch_pnl()

if not all_trades:
    st.error("Inga trades. Kontrollera API-nycklar."); st.stop()

# --- DATA VALIDATION ---
def validate_trades(trades):
    """Validerar och rensar API-data. Returnerar (clean_trades, warnings)."""
    clean = []
    warnings = []
    seen_ids = set()

    for t in trades:
        tid = t.get('tradeId', '')
        symbol = t.get('symbol', '?')
        date = (t.get('tradeDate') or '').split('T')[0]
        price = float(t.get('price') or 0)
        qty = float(t.get('qty') or 0)
        gross = float(t.get('grossProceeds') or 0)
        side = str(t.get('side', '')).strip()

        # Duplikat-check
        if tid in seen_ids:
            warnings.append(f"⚠️ Duplikat: {symbol} {date} (ID: {tid})")
            continue
        seen_ids.add(tid)

        # Cancelled trades
        if t.get('canceled', False):
            warnings.append(f"⚠️ Cancelerad: {symbol} {date}")
            continue

        # Saknar nödvändig data
        if not symbol or not side:
            warnings.append(f"⚠️ Saknar symbol/side: ID {tid}")
            continue

        # Pris/antal = 0
        if price <= 0 or qty <= 0:
            warnings.append(f"⚠️ Pris/antal = 0: {symbol} {date} (pris={price}, qty={qty})")
            continue

        # Korsvalidering: price * qty vs grossProceeds (tillåt 5% avvikelse)
        expected_gross = price * qty
        if gross != 0 and expected_gross > 0:
            deviation = abs(abs(gross) - expected_gross) / expected_gross
            if deviation > 0.05:
                warnings.append(
                    f"⚠️ Avvikelse {symbol} {date}: "
                    f"pris×antal=${expected_gross:.2f} vs gross=${gross:.2f} ({deviation*100:.0f}%)")

        # Orimligt högt pris (> $50,000 per aktie)
        if price > 50000:
            warnings.append(f"⚠️ Misstänkt högt pris: {symbol} {date} @ ${price:,.2f}")

        # Okänd side
        mapped = SIDE_MAP.get(side.upper())
        if not mapped:
            warnings.append(f"⚠️ Okänd side '{side}': {symbol} {date}")

        clean.append(t)

    return clean, warnings

all_trades, data_warnings = validate_trades(all_trades)

# Show validation status
if data_warnings:
    with st.expander(f"⚠️ DATAVALIDERING — {len(data_warnings)} varningar", expanded=False):
        for w in data_warnings[:50]:
            st.markdown(f'<div style="font-family:Space Mono,monospace;font-size:0.75rem;color:#ff6633;padding:3px 0;">{w}</div>', unsafe_allow_html=True)
        if len(data_warnings) > 50:
            st.caption(f"... och {len(data_warnings)-50} till")

res_df = compute_fifo(all_trades)

# Validate FIFO output
if not res_df.empty:
    fifo_warnings = []
    # Flag trades with unreasonable P/L (> $10,000 on a single close)
    extreme = res_df[res_df['Vinst ($)'].abs() > 10000]
    for _, r in extreme.iterrows():
        fifo_warnings.append(f"🔴 Extremt P/L: {r['Ticker']} {r['Datum']} ${r['Vinst ($)']:+,.0f} ({r['Vinst %']:+.1f}%)")
    # Flag unreasonable % (> 500%)
    extreme_pct = res_df[res_df['Vinst %'].abs() > 500]
    for _, r in extreme_pct.iterrows():
        if r['Ticker'] not in extreme['Ticker'].values:
            fifo_warnings.append(f"🔴 Extrem %: {r['Ticker']} {r['Datum']} {r['Vinst %']:+.1f}%")

    if fifo_warnings:
        with st.expander(f"🔴 FIFO-VARNINGAR — {len(fifo_warnings)} misstänkta trades", expanded=False):
            st.markdown('<div style="font-family:Space Mono,monospace;font-size:0.75rem;color:#9999aa;margin-bottom:8px;">Dessa trades har ovanligt stora värden — kontrollera rådata.</div>', unsafe_allow_html=True)
            for w in fifo_warnings:
                st.markdown(f'<div style="font-family:Space Mono,monospace;font-size:0.75rem;color:#ff3366;padding:3px 0;">{w}</div>', unsafe_allow_html=True)

# Apply filters
if not res_df.empty:
    res_df['Datum_dt'] = pd.to_datetime(res_df['Datum'], errors='coerce')
    # Add annotations to dataframe
    res_df['_key'] = res_df.apply(trade_key, axis=1)
    res_df['Strategi'] = res_df['_key'].map(lambda k: annotations.get(k, {}).get('strategy', '–'))
    res_df['Betyg']    = res_df['_key'].map(lambda k: annotations.get(k, {}).get('grade', '–'))

    mask = ((res_df['Datum_dt'] >= pd.Timestamp(date_from)) & (res_df['Datum_dt'] <= pd.Timestamp(date_to)))
    dir_mask = pd.Series(False, index=res_df.index)
    if show_long:  dir_mask |= (res_df['Riktning'] == 'LONG')
    if show_short: dir_mask |= (res_df['Riktning'] == 'SHORT')
    strat_mask = res_df['Strategi'].str.contains(strat_filter.split("/")[0].strip()) if strat_filter != "Alla" else True
    filtered = res_df[mask & dir_mask & strat_mask].copy()
else:
    filtered = pd.DataFrame()


# --- LIVE P&L ---
day_realized   = float(pnl_data.get('dayRealized', 0) or 0)
day_unrealized = float(pnl_data.get('totalUnrealized', 0) or 0)
day_total      = float(pnl_data.get('dayPnl', 0) or 0)

st.markdown('<div class="section-header"><span class="live-dot"></span>DAGENS P&L — LIVE</div>', unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)
with c1: st.markdown(mcard("REALISERAT IDAG", day_realized, "dollar"), unsafe_allow_html=True)
with c2: st.markdown(mcard("OREALISERAT", day_unrealized, "dollar"), unsafe_allow_html=True)
with c3: st.markdown(mcard("TOTALT IDAG", day_total, "dollar"), unsafe_allow_html=True)

positions_data = fetch_positions()
open_pos = [p for p in positions_data if abs(float(p.get('shares',0) or 0)) > 0.01]
longs  = [p for p in open_pos if float(p.get('shares',0) or 0) > 0]
shorts = [p for p in open_pos if float(p.get('shares',0) or 0) < 0]
st.markdown('<div class="section-header">ÖPPNA POSITIONER</div>', unsafe_allow_html=True)
p1, p2 = st.columns(2)
with p1: st.markdown(mcard("LONG", len(longs), "int", sub=" | ".join(p['symbol'] for p in longs) or "–"), unsafe_allow_html=True)
with p2: st.markdown(mcard("SHORT", len(shorts), "int", sub=" | ".join(p['symbol'] for p in shorts) or "–"), unsafe_allow_html=True)

# --- NEWS ---
if open_pos:
    with st.expander("📰 NYHETER OM ÖPPNA POSITIONER", expanded=False):
        open_tickers = [p['symbol'] for p in open_pos]
        with st.spinner("Hämtar nyheter..."):
            news_items = fetch_news(open_tickers)
        if news_items:
            for ticker in open_tickers:
                ticker_news = [n for n in news_items if n['ticker'] == ticker]
                if ticker_news:
                    st.markdown(f'<div class="section-header">{ticker}</div>', unsafe_allow_html=True)
                    for n in ticker_news:
                        link = f' <a href="{n["url"]}" target="_blank" style="color:#00ff88;text-decoration:none;">→ läs</a>' if n['url'] else ''
                        st.markdown(
                            f'<div style="padding:8px 0;border-bottom:1px solid #1e1e2e;">'
                            f'<span style="font-family:Space Mono,monospace;font-size:0.85rem;color:#e8e8f0;">{n["title"]}</span>'
                            f'<br><span style="font-family:Space Mono,monospace;font-size:0.7rem;color:#555570;">{n["date"]}  •  {n["provider"]}</span>'
                            f'{link}</div>',
                            unsafe_allow_html=True)
        else:
            st.info("Inga nyheter hittades.")


# --- COURTAGE (from raw API data) ---
courtage_df = pd.DataFrame([{
    'Datum': (t.get('tradeDate') or '').split('T')[0],
    'Courtage': float(t.get('totalFees') or 0) + float(t.get('commission') or 0),
} for t in all_trades])
courtage_df['Datum_dt'] = pd.to_datetime(courtage_df['Datum'], errors='coerce')
courtage_df = courtage_df[(courtage_df['Datum_dt'] >= pd.Timestamp(date_from)) &
                           (courtage_df['Datum_dt'] <= pd.Timestamp(date_to))]
total_courtage = courtage_df['Courtage'].sum()

# --- PERIOD STATS ---
if not filtered.empty:
    wins_df = filtered[filtered['Vinst ($)'] > 0]
    losses_df = filtered[filtered['Vinst ($)'] < 0]
    total_pnl = filtered['Vinst ($)'].sum()
    wins, losses, total = len(wins_df), len(losses_df), len(filtered)
    win_rate = wins/total*100 if total > 0 else 0
    avg_win_dollar  = wins_df['Vinst ($)'].mean() if wins > 0 else 0
    avg_loss_dollar = losses_df['Vinst ($)'].mean() if losses > 0 else 0
    avg_win_pct  = wins_df['Vinst %'].mean() if wins > 0 else 0
    avg_loss_pct = losses_df['Vinst %'].mean() if losses > 0 else 0
    rr = abs(avg_win_dollar/avg_loss_dollar) if avg_loss_dollar != 0 else 0
    avg_win_time  = wins_df['Hålltid (min)'].dropna().mean() if wins > 0 else None
    avg_loss_time = losses_df['Hålltid (min)'].dropna().mean() if losses > 0 else None

    st.markdown('<div class="section-header">PERIOD STATISTIK</div>', unsafe_allow_html=True)
    row1 = st.columns(4)
    for col, (label, val, fmt) in zip(row1, [
        ("NETTO P/L", total_pnl, "dollar"), ("WIN RATE", win_rate, "pct"),
        ("TRADES", total, "int"), ("RISK/REWARD", rr, "x"),
    ]):
        with col: st.markdown(mcard(label, val, fmt), unsafe_allow_html=True)

    row2 = st.columns(4)
    for col, (label, val, fmt) in zip(row2, [
        ("SNITTVINST", avg_win_dollar, "dollar"), ("SNITTFÖRLUST", avg_loss_dollar, "dollar"),
        ("SNITTVINST", avg_win_pct, "pct"), ("SNITTFÖRLUST", avg_loss_pct, "pct"),
    ]):
        with col: st.markdown(mcard(label, val, fmt), unsafe_allow_html=True)

    st.markdown('<div class="section-header">GENOMSNITTLIG HÅLLTID</div>', unsafe_allow_html=True)
    t1, t2, t3 = st.columns(3)
    with t1: st.markdown(mcard("VINNANDE", avg_win_time or 0, "time"), unsafe_allow_html=True)
    with t2: st.markdown(mcard("FÖRLORANDE", avg_loss_time or 0, "time"), unsafe_allow_html=True)
    all_time = filtered['Hålltid (min)'].dropna().mean()
    with t3: st.markdown(mcard("ALLA", all_time or 0, "time"), unsafe_allow_html=True)

    # Courtage
    st.markdown('<div class="section-header">COURTAGE</div>', unsafe_allow_html=True)
    daily_courtage = courtage_df.groupby('Datum')['Courtage'].sum().reset_index().sort_values('Datum')
    avg_daily_c = daily_courtage['Courtage'].mean() if not daily_courtage.empty else 0
    monthly_courtage = courtage_df.copy()
    monthly_courtage['Månad'] = monthly_courtage['Datum_dt'].dt.to_period('M').astype(str)
    avg_monthly_c = monthly_courtage.groupby('Månad')['Courtage'].sum().mean() if not monthly_courtage.empty else 0

    cc1, cc2, cc3, cc4 = st.columns(4)
    with cc1: st.markdown(mcard("TOTALT COURTAGE", -total_courtage, "dollar"), unsafe_allow_html=True)
    with cc2: st.markdown(mcard("SNITT / DAG", -avg_daily_c, "dollar"), unsafe_allow_html=True)
    with cc3: st.markdown(mcard("SNITT / MÅNAD", -avg_monthly_c, "dollar"), unsafe_allow_html=True)
    with cc4: st.markdown(mcard("NETTO EFTER COURTAGE", total_pnl - total_courtage, "dollar"), unsafe_allow_html=True)


# --- TABS ---
st.markdown('<div class="section-header">ANALYS</div>', unsafe_allow_html=True)
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["P/L KURVA", "INSIKTER", "PER TICKER", "MÅNADER", "ALLA TRADES", "RAW DATA"])


with tab1:
    if not filtered.empty:
        daily = filtered.groupby('Datum')['Vinst ($)'].sum().reset_index().sort_values('Datum')
        daily['Kumulativ'] = daily['Vinst ($)'].cumsum()
        daily['Peak'] = daily['Kumulativ'].cummax()
        daily['Drawdown'] = daily['Kumulativ'] - daily['Peak']

        # Equity curve + drawdown
        from plotly.subplots import make_subplots
        fig_eq = make_subplots(rows=2, cols=1, shared_xaxes=True,
            vertical_spacing=0.05, row_heights=[0.7, 0.3],
            subplot_titles=['Equity Curve', 'Drawdown'])

        fig_eq.add_trace(go.Scatter(x=daily['Datum'], y=daily['Kumulativ'],
            fill='tozeroy', fillcolor='rgba(0,255,136,0.05)',
            line=dict(color='#00ff88', width=2), name='P/L',
            hovertemplate='%{x}<br>$%{y:,.0f}<extra></extra>'), row=1, col=1)
        fig_eq.add_trace(go.Scatter(x=daily['Datum'], y=daily['Peak'],
            line=dict(color='#333366', width=1, dash='dot'), name='Peak',
            hovertemplate='Peak: $%{y:,.0f}<extra></extra>'), row=1, col=1)
        fig_eq.add_hline(y=0, line_dash='dot', line_color='#333344', row=1, col=1)

        fig_eq.add_trace(go.Scatter(x=daily['Datum'], y=daily['Drawdown'],
            fill='tozeroy', fillcolor='rgba(255,51,102,0.15)',
            line=dict(color='#ff3366', width=1.5), name='Drawdown',
            hovertemplate='%{x}<br>$%{y:,.0f}<extra></extra>'), row=2, col=1)

        fig_eq.update_layout(**PLOTLY_LAYOUT, height=450, showlegend=False)
        fig_eq.update_annotations(font=dict(color='#9999aa', family='Space Mono', size=12))
        st.plotly_chart(fig_eq, width='stretch')

        # Drawdown stats
        max_dd = daily['Drawdown'].min()
        max_dd_date = daily.loc[daily['Drawdown'].idxmin(), 'Datum'] if max_dd < 0 else '–'
        current_dd = daily['Drawdown'].iloc[-1] if len(daily) > 0 else 0

        d1, d2, d3 = st.columns(3)
        with d1: st.markdown(mcard("MAX DRAWDOWN", max_dd, "dollar"), unsafe_allow_html=True)
        with d2: st.markdown(mcard("NUVARANDE DRAWDOWN", current_dd, "dollar"), unsafe_allow_html=True)
        with d3: st.markdown(mcard("MAX DD DATUM", 0, "raw", sub=str(max_dd_date)), unsafe_allow_html=True)

        # Daily P/L bars
        st.markdown('<div class="section-header">DAGLIG P/L</div>', unsafe_allow_html=True)
        colors = ['#00ff88' if v > 0 else '#ff3366' for v in daily['Vinst ($)']]
        fig2 = go.Figure(go.Bar(x=daily['Datum'], y=daily['Vinst ($)'],
            marker_color=colors, hovertemplate='%{x}<br>$%{y:,.0f}<extra></extra>'))
        fig2.update_layout(**PLOTLY_LAYOUT, height=250)
        st.plotly_chart(fig2, width='stretch')
    else: st.info("Inga trades i valt intervall.")


with tab2:
    if not filtered.empty:
        daily = filtered.groupby('Datum')['Vinst ($)'].sum().reset_index().sort_values('Datum')
        daily['Datum_dt'] = pd.to_datetime(daily['Datum'])
        daily['Veckodag'] = daily['Datum_dt'].dt.day_name()

        # --- BÄSTA / SÄMSTA DAGAR ---
        st.markdown('<div class="section-header">BÄSTA & SÄMSTA DAGAR</div>', unsafe_allow_html=True)
        top5 = daily.nlargest(5, 'Vinst ($)')
        bottom5 = daily.nsmallest(5, 'Vinst ($)')

        col_best, col_worst = st.columns(2)
        with col_best:
            st.markdown('<div style="font-family:Space Mono,monospace;font-size:0.85rem;color:#00ff88;margin-bottom:0.5rem;">TOP 5 DAGAR</div>', unsafe_allow_html=True)
            for _, r in top5.iterrows():
                st.markdown(f'<div style="font-family:Space Mono,monospace;font-size:0.85rem;padding:6px 0;border-bottom:1px solid #1e1e2e;color:#e8e8f0;">{r["Datum"]}  <span style="color:#00ff88;font-weight:700;">${r["Vinst ($)"]:+,.0f}</span></div>', unsafe_allow_html=True)
        with col_worst:
            st.markdown('<div style="font-family:Space Mono,monospace;font-size:0.85rem;color:#ff3366;margin-bottom:0.5rem;">SÄMSTA 5 DAGAR</div>', unsafe_allow_html=True)
            for _, r in bottom5.iterrows():
                st.markdown(f'<div style="font-family:Space Mono,monospace;font-size:0.85rem;padding:6px 0;border-bottom:1px solid #1e1e2e;color:#e8e8f0;">{r["Datum"]}  <span style="color:#ff3366;font-weight:700;">${r["Vinst ($)"]:+,.0f}</span></div>', unsafe_allow_html=True)

        # --- STREAKS ---
        st.markdown('<div class="section-header">STREAKS</div>', unsafe_allow_html=True)
        streak_type, current_streak, max_win_streak, max_loss_streak = None, 0, 0, 0
        curr_win, curr_loss = 0, 0
        for _, r in daily.iterrows():
            if r['Vinst ($)'] > 0:
                curr_win += 1
                curr_loss = 0
                max_win_streak = max(max_win_streak, curr_win)
            elif r['Vinst ($)'] < 0:
                curr_loss += 1
                curr_win = 0
                max_loss_streak = max(max_loss_streak, curr_loss)
            else:
                curr_win = curr_loss = 0

        # Current streak
        curr_streak_val, curr_streak_type = 0, "–"
        for _, r in daily.iloc[::-1].iterrows():
            if curr_streak_val == 0:
                curr_streak_type = "VINST" if r['Vinst ($)'] > 0 else "FÖRLUST"
            if (curr_streak_type == "VINST" and r['Vinst ($)'] > 0) or \
               (curr_streak_type == "FÖRLUST" and r['Vinst ($)'] < 0):
                curr_streak_val += 1
            else:
                break

        s1, s2, s3 = st.columns(3)
        with s1: st.markdown(mcard("LÄNGSTA VINSTSVIT", max_win_streak, "int", sub="dagar i rad"), unsafe_allow_html=True)
        with s2: st.markdown(mcard("LÄNGSTA FÖRLUSTSVIT", max_loss_streak, "int", sub="dagar i rad"), unsafe_allow_html=True)
        with s3:
            streak_color = "#00ff88" if curr_streak_type == "VINST" else "#ff3366"
            st.markdown(
                f'<div class="metric-card"><div class="metric-label">NUVARANDE STREAK</div>'
                f'<div class="metric-value" style="color:{streak_color};">{curr_streak_val}</div>'
                f'<div class="metric-sub">{curr_streak_type}-dagar i rad</div></div>',
                unsafe_allow_html=True)

        # --- VECKODAG ---
        st.markdown('<div class="section-header">AVKASTNING PER VECKODAG</div>', unsafe_allow_html=True)

        weekday_order = ['Monday','Tuesday','Wednesday','Thursday','Friday']
        weekday_sv = {'Monday':'Måndag','Tuesday':'Tisdag','Wednesday':'Onsdag','Thursday':'Torsdag','Friday':'Fredag'}
        by_weekday = daily.groupby('Veckodag').agg(
            Dagar=('Vinst ($)','count'),
            Total=('Vinst ($)','sum'),
            Snitt=('Vinst ($)','mean'),
            WinRate=('Vinst ($)', lambda x: (x>0).sum()/len(x)*100),
        ).reindex(weekday_order).dropna().reset_index()
        by_weekday['Snitt'] = by_weekday['Snitt'].round(0)
        by_weekday['WinRate'] = by_weekday['WinRate'].round(1)
        by_weekday['Dag'] = by_weekday['Veckodag'].map(weekday_sv)

        colors_wd = ['#00ff88' if v > 0 else '#ff3366' for v in by_weekday['Snitt']]
        fig_wd = go.Figure(go.Bar(x=by_weekday['Dag'], y=by_weekday['Snitt'],
            marker_color=colors_wd,
            text=[f"${v:+,.0f}" for v in by_weekday['Snitt']], textposition='outside',
            textfont=dict(color=colors_wd),
            hovertemplate='%{x}<br>Snitt: $%{y:,.0f}<extra></extra>'))
        fig_wd.update_layout(**PLOTLY_LAYOUT, height=280, title='Snittavkastning per veckodag',
                             xaxis_type='category')
        st.plotly_chart(fig_wd, width='stretch')

        cols_wd = st.columns(len(by_weekday))
        for col, (_, r) in zip(cols_wd, by_weekday.iterrows()):
            with col:
                st.markdown(mcard(r['Dag'].upper(), r['Snitt'], "dollar",
                    sub=f"{int(r['Dagar'])}d | {r['WinRate']:.0f}% win"),
                    unsafe_allow_html=True)

    else: st.info("Inga trades i valt intervall.")


with tab3:
    if not filtered.empty:
        by_ticker = filtered.groupby('Ticker').agg(
            PnL=('Vinst ($)','sum'), Trades=('Vinst ($)','count'),
            Vinster=('Vinst ($)', lambda x: (x>0).sum()),
            AvgPct=('Vinst %','mean'),
        ).reset_index().sort_values('PnL', ascending=False)
        by_ticker['Win%'] = (by_ticker['Vinster']/by_ticker['Trades']*100).round(1)
        by_ticker['PnL'] = by_ticker['PnL'].round(2)
        by_ticker['AvgPct'] = by_ticker['AvgPct'].round(1)
        by_ticker['AbsTrades'] = by_ticker['Trades']
        by_ticker['Label'] = by_ticker.apply(
            lambda r: f"{r['Ticker']}<br>{r['AvgPct']:+.1f}%<br>${r['PnL']:+,.0f}", axis=1)
        fig3 = px.treemap(by_ticker, path=['Label'], values='AbsTrades', color='AvgPct',
            color_continuous_scale=[[0,'#ff3366'],[0.4,'#ff6633'],[0.5,'#444444'],[0.6,'#33aa66'],[1,'#00ff88']],
            color_continuous_midpoint=0)
        fig3.update_layout(**PLOTLY_LAYOUT, height=450, title='P/L per Ticker',
            coloraxis_colorbar=dict(title='Avg %', tickfont=dict(color='#888899')))
        fig3.update_traces(textfont=dict(family='Space Mono', size=11),
            marker=dict(line=dict(width=1, color='#1e1e2e')))
        st.plotly_chart(fig3, width='stretch')
        st.dataframe(by_ticker[['Ticker','PnL','Trades','Win%','AvgPct']].rename(
            columns={'PnL':'P/L ($)','AvgPct':'Avg %'}), width='stretch', hide_index=True)
    else: st.info("Inga trades i valt intervall.")


with tab4:
    if not filtered.empty:
        monthly = filtered.copy()
        monthly['Månad'] = monthly['Datum_dt'].dt.to_period('M').astype(str)
        by_month = monthly.groupby('Månad').agg(
            Trades=('Vinst ($)','count'), PnL=('Vinst ($)','sum'),
            Vinster=('Vinst ($)', lambda x: (x>0).sum()),
            Förluster=('Vinst ($)', lambda x: (x<0).sum()),
            AvgVinstPct=('Vinst %', lambda x: x[x>0].mean() if (x>0).any() else 0),
            AvgFörlustPct=('Vinst %', lambda x: x[x<0].mean() if (x<0).any() else 0),
        ).reset_index()
        by_month['Win%'] = (by_month['Vinster']/by_month['Trades']*100).round(1)
        by_month['PnL']  = by_month['PnL'].round(2)
        by_month['AvgVinstPct']   = by_month['AvgVinstPct'].round(1)
        by_month['AvgFörlustPct'] = by_month['AvgFörlustPct'].round(1)

        # Add courtage per month
        mc = courtage_df.copy()
        mc['Månad'] = mc['Datum_dt'].dt.to_period('M').astype(str)
        monthly_c = mc.groupby('Månad')['Courtage'].sum().reset_index()
        by_month = by_month.merge(monthly_c, on='Månad', how='left').fillna(0)
        by_month['Courtage'] = by_month['Courtage'].round(2)
        by_month['Netto'] = (by_month['PnL'] - by_month['Courtage']).round(2)

        colors = ['#00ff88' if v > 0 else '#ff3366' for v in by_month['Netto']]
        fig4 = go.Figure(go.Bar(x=by_month['Månad'], y=by_month['Netto'], marker_color=colors,
            hovertemplate='%{x}<br>$%{y:,.0f}<extra></extra>',
            text=[f"${v:+,.0f}" for v in by_month['Netto']], textposition='outside',
            textfont=dict(color=['#00ff88' if v > 0 else '#ff3366' for v in by_month['Netto']])))
        fig4.update_layout(**PLOTLY_LAYOUT, height=280, title='Månadsvis P/L (efter courtage)', xaxis_type='category')
        st.plotly_chart(fig4, width='stretch')
        st.dataframe(by_month[['Månad','Trades','Vinster','Förluster','Win%','PnL','Courtage','Netto','AvgVinstPct','AvgFörlustPct']]
            .rename(columns={'PnL':'Brutto ($)','Courtage':'Courtage ($)','Netto':'Netto ($)',
                             'AvgVinstPct':'Avg Vinst %','AvgFörlustPct':'Avg Förlust %'}),
            width='stretch', hide_index=True)
    else: st.info("Inga trades i valt intervall.")


with tab5:
    if not filtered.empty:
        # --- Trade list ---
        display = filtered[['Datum','Entry Datum','Ticker','Riktning','Vinst ($)','Vinst %','Hålltid (min)']].copy()
        display['_key'] = filtered['_key']
        display['Strategi'] = display['_key'].map(lambda k: st.session_state.annotations.get(k, {}).get('strategy', '–'))
        display['Betyg']    = display['_key'].map(lambda k: st.session_state.annotations.get(k, {}).get('grade', '–'))
        display['Hålltid']  = display['Hålltid (min)'].apply(fmt_duration)
        display_show = display.drop(columns=['Hålltid (min)', '_key']).sort_values('Datum', ascending=False)
        def color_pnl(val):
            if isinstance(val, (int, float)):
                return f'color: {"#00ff88" if val > 0 else "#ff3366" if val < 0 else "#888899"};'
            return ''
        styled = display_show.style.map(color_pnl, subset=['Vinst ($)', 'Vinst %'])\
                              .format({'Vinst ($)': '{:+,.2f}', 'Vinst %': '{:+.1f}%'})
        st.dataframe(styled, width='stretch', hide_index=True, height=400)

        # --- Trade detail selector ---
        st.markdown('<div class="section-header">TRADE DETALJ — VÄLJ TRADE</div>', unsafe_allow_html=True)

        show_graded = st.checkbox("Visa redan betygsatta", value=False)

        sorted_trades = filtered.sort_values('Datum', ascending=False)
        # Filter out already graded trades unless checkbox is checked
        if not show_graded:
            ungraded_mask = sorted_trades['_key'].map(
                lambda k: st.session_state.annotations.get(k, {}).get('grade', '–') == '–')
            selectable = sorted_trades[ungraded_mask]
        else:
            selectable = sorted_trades

        if selectable.empty:
            st.success("🎉 Alla trades är betygsatta!")
        else:
            trade_options = []
            for _, r in selectable.iterrows():
                pnl_sign = "✅" if r['Vinst ($)'] > 0 else "❌"
                strat_tag = f" [{st.session_state.annotations.get(r['_key'],{}).get('strategy','–')}]" if st.session_state.annotations.get(r['_key'],{}).get('strategy','–') != '–' else ""
                grade_tag = f" ({st.session_state.annotations.get(r['_key'],{}).get('grade','–')})" if st.session_state.annotations.get(r['_key'],{}).get('grade','–') != '–' else ""
                trade_options.append(f"{pnl_sign} {r['Ticker']}  {r['Entry Datum']} → {r['Datum']}  ${r['Vinst ($)']:+,.0f}  {r['Riktning']}{strat_tag}{grade_tag}")

            selected_idx = st.selectbox("Trade", range(len(trade_options)),
                format_func=lambda i: trade_options[i], label_visibility="collapsed")
            trade = selectable.iloc[selected_idx]
            tk = trade_key(trade)

            # Strategy + Grade + Save
            col_s, col_g, col_save = st.columns([2, 2, 1])
            with col_s:
                curr_strat = st.session_state.annotations.get(tk, {}).get('strategy', '–')
                new_strat = st.selectbox("Strategi", STRATEGIES,
                    index=STRATEGIES.index(curr_strat) if curr_strat in STRATEGIES else 0,
                    key=f"strat_{tk}")
            with col_g:
                curr_grade = st.session_state.annotations.get(tk, {}).get('grade', '–')
                new_grade = st.selectbox("Betyg", GRADES,
                    index=GRADES.index(curr_grade) if curr_grade in GRADES else 0,
                    key=f"grade_{tk}")
            with col_save:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("💾 SPARA", key=f"save_{tk}"):
                    if tk not in st.session_state.annotations:
                        st.session_state.annotations[tk] = {}
                    st.session_state.annotations[tk]['strategy'] = new_strat
                    st.session_state.annotations[tk]['grade'] = new_grade
                    saved = save_annotations()
                    if saved:
                        st.success(f"Sparad: {trade['Ticker']} — {new_strat} / {new_grade}")
                    else:
                        st.warning("Sparad i sessionen. Exportera JSON för att behålla.")
                    st.rerun()

            # Trade info cards
            col_i1, col_i2, col_i3, col_i4 = st.columns(4)
            with col_i1: st.markdown(mcard("P/L", trade['Vinst ($)'], "dollar"), unsafe_allow_html=True)
            with col_i2: st.markdown(mcard("VINST %", trade['Vinst %'], "pct"), unsafe_allow_html=True)
            with col_i3: st.markdown(mcard("RIKTNING", 0, "raw", sub=trade['Riktning']), unsafe_allow_html=True)
            with col_i4: st.markdown(mcard("HÅLLTID", trade.get('Hålltid (min)') or 0, "time"), unsafe_allow_html=True)

            # Chart
            st.markdown('<div class="section-header">KURSGRAF</div>', unsafe_allow_html=True)
            with st.spinner(f"Hämtar kursdata för {trade['Ticker']}..."):
                chart_df = fetch_chart_data(trade['Ticker'], trade['Entry Datum'], trade['Datum'])

            if chart_df is not None and not isinstance(chart_df, str) and not chart_df.empty:
                from plotly.subplots import make_subplots
                fig_chart = make_subplots(rows=2, cols=1, shared_xaxes=True,
                    vertical_spacing=0.03, row_heights=[0.75, 0.25])
                fig_chart.add_trace(go.Candlestick(
                    x=chart_df['Date'], open=chart_df['Open'], high=chart_df['High'],
                    low=chart_df['Low'], close=chart_df['Close'],
                    increasing_line_color='#00ff88', decreasing_line_color='#ff3366',
                    increasing_fillcolor='#00ff88', decreasing_fillcolor='#ff3366',
                    name='Pris'), row=1, col=1)
                if 'Volume' in chart_df.columns and chart_df['Volume'].sum() > 0:
                    vol_colors = ['#00ff88' if c >= o else '#ff3366'
                                  for c, o in zip(chart_df['Close'], chart_df['Open'])]
                    fig_chart.add_trace(go.Bar(x=chart_df['Date'], y=chart_df['Volume'],
                        marker_color=vol_colors, opacity=0.4, showlegend=False), row=2, col=1)
                entry_dt = pd.to_datetime(trade['Entry Datum'])
                exit_dt  = pd.to_datetime(trade['Datum'])
                entry_color = '#00ff88' if trade['Riktning'] == 'LONG' else '#ff3366'
                exit_color  = '#ff3366' if trade['Riktning'] == 'LONG' else '#00ff88'
                entry_row = chart_df[chart_df['Date'] >= entry_dt].head(1)
                exit_row  = chart_df[chart_df['Date'] >= exit_dt].head(1)
                if not entry_row.empty:
                    fig_chart.add_trace(go.Scatter(
                        x=[entry_row['Date'].iloc[0]], y=[float(entry_row['Low'].iloc[0]) * 0.98],
                        mode='markers+text', marker=dict(symbol='triangle-up', size=16, color=entry_color),
                        text=['ENTRY'], textposition='bottom center', textfont=dict(color=entry_color, size=10),
                        showlegend=False), row=1, col=1)
                if not exit_row.empty:
                    fig_chart.add_trace(go.Scatter(
                        x=[exit_row['Date'].iloc[0]], y=[float(exit_row['High'].iloc[0]) * 1.02],
                        mode='markers+text', marker=dict(symbol='triangle-down', size=16, color=exit_color),
                        text=['EXIT'], textposition='top center', textfont=dict(color=exit_color, size=10),
                        showlegend=False), row=1, col=1)
                fig_chart.update_layout(**PLOTLY_LAYOUT, height=500,
                    title=f"{trade['Ticker']} — {trade['Entry Datum']} → {trade['Datum']}",
                    xaxis_rangeslider_visible=False,
                    xaxis_rangebreaks=[dict(bounds=["sat","mon"])],
                    yaxis2=dict(gridcolor='#1e1e2e', linecolor='#1e1e2e', title='Volym'),
                    showlegend=False)
                st.plotly_chart(fig_chart, width='stretch')
            else:
                if isinstance(chart_df, str):
                    st.warning(f"Kunde inte hämta kursdata för {trade['Ticker']}: {chart_df}")
                else:
                    st.warning(f"Ingen kursdata tillgänglig för {trade['Ticker']}")

            # Notes
            curr_notes = st.session_state.annotations.get(tk, {}).get('notes', '')
            new_notes = st.text_area("Anteckningar", value=curr_notes, key=f"notes_{tk}", height=80,
                                      placeholder="Skriv anteckningar om denna trade...")
            if st.button("💾 SPARA ANTECKNING", key=f"savenote_{tk}"):
                if tk not in st.session_state.annotations: st.session_state.annotations[tk] = {}
                st.session_state.annotations[tk]['notes'] = new_notes
                save_annotations()
                st.success("Anteckning sparad")
                st.rerun()
    else:
        st.info("Inga trades i valt intervall.")


with tab6:
    raw_df = pd.DataFrame([{
        'Datum': (t.get('tradeDate') or '').split('T')[0], 'Tid': t.get('execTime',''),
        'Symbol': t.get('symbol'), 'Side': t.get('side'),
        'Qty': t.get('qty'), 'Pris': t.get('price'), 'Netto': t.get('netProceeds'),
        'TradeID': t.get('tradeId'),
    } for t in all_trades])
    ticker_filter = st.selectbox("Filtrera ticker",
        options=['Alla'] + sorted(raw_df['Symbol'].dropna().unique().tolist()))
    if ticker_filter != 'Alla': raw_df = raw_df[raw_df['Symbol'] == ticker_filter]
    st.dataframe(raw_df.sort_values(['Datum','Tid'], ascending=False), width='stretch', hide_index=True, height=500)
    st.caption(f"{len(raw_df)} rader | Rådata direkt från TradeZero API")


# --- STRATEGY & GRADE STATS (bottom) ---
if not filtered.empty:
    # Re-read annotations for filtered data
    filtered_ann = filtered.copy()
    filtered_ann['Strategi'] = filtered_ann['_key'].map(lambda k: st.session_state.annotations.get(k, {}).get('strategy', '–'))
    filtered_ann['Betyg'] = filtered_ann['_key'].map(lambda k: st.session_state.annotations.get(k, {}).get('grade', '–'))

    tagged_strat = filtered_ann[filtered_ann['Strategi'] != '–']
    tagged_grade = filtered_ann[filtered_ann['Betyg'] != '–']

    if not tagged_strat.empty:
        st.markdown('<div class="section-header">STATISTIK PER STRATEGI</div>', unsafe_allow_html=True)
        by_strat = tagged_strat.groupby('Strategi').agg(
            Trades=('Vinst ($)', 'count'), PnL=('Vinst ($)', 'sum'),
            WinRate=('Vinst ($)', lambda x: (x>0).sum()/len(x)*100),
            AvgPct=('Vinst %', 'mean'),
            AvgHåll=('Hålltid (min)', lambda x: x.dropna().mean()),
        ).reset_index()
        by_strat['PnL']     = by_strat['PnL'].round(0)
        by_strat['WinRate'] = by_strat['WinRate'].round(1)
        by_strat['AvgPct']  = by_strat['AvgPct'].round(1)

        cols = st.columns(len(by_strat))
        for col, (_, row) in zip(cols, by_strat.iterrows()):
            with col:
                st.markdown(mcard(row['Strategi'].split("/")[0].strip().upper(),
                    row['PnL'], "dollar",
                    sub=f"{int(row['Trades'])} trades | {row['WinRate']:.0f}% win | avg {row['AvgPct']:+.0f}% | {fmt_duration(row['AvgHåll'])}"),
                    unsafe_allow_html=True)

    if not tagged_grade.empty:
        st.markdown('<div class="section-header">STATISTIK PER BETYG</div>', unsafe_allow_html=True)
        grade_order = ['A', 'B', 'C', 'F']
        by_grade = tagged_grade.groupby('Betyg').agg(
            Trades=('Vinst ($)', 'count'), PnL=('Vinst ($)', 'sum'),
            WinRate=('Vinst ($)', lambda x: (x>0).sum()/len(x)*100),
            AvgPct=('Vinst %', 'mean'),
            AvgDollar=('Vinst ($)', 'mean'),
            AvgHåll=('Hålltid (min)', lambda x: x.dropna().mean()),
        ).reset_index()
        by_grade['PnL']       = by_grade['PnL'].round(0)
        by_grade['WinRate']   = by_grade['WinRate'].round(1)
        by_grade['AvgPct']    = by_grade['AvgPct'].round(1)
        by_grade['AvgDollar'] = by_grade['AvgDollar'].round(0)
        # Sort by grade order
        by_grade['_sort'] = by_grade['Betyg'].map(lambda g: grade_order.index(g) if g in grade_order else 99)
        by_grade = by_grade.sort_values('_sort')

        cols = st.columns(len(by_grade))
        for col, (_, row) in zip(cols, by_grade.iterrows()):
            grade_color = {'A':'#00ff88','B':'#33aa66','C':'#ff6633','F':'#ff3366'}.get(row['Betyg'],'#888899')
            with col:
                st.markdown(
                    f'<div class="metric-card">'
                    f'<div class="metric-label">BETYG</div>'
                    f'<div class="metric-value" style="color:{grade_color};font-size:2rem;">{row["Betyg"]}</div>'
                    f'<div class="metric-sub" style="color:#9999aa;line-height:1.8;">'
                    f'{int(row["Trades"])} trades<br>'
                    f'Win rate: {row["WinRate"]:.0f}%<br>'
                    f'Snitt: {row["AvgPct"]:+.0f}% / ${row["AvgDollar"]:+,.0f}<br>'
                    f'Hålltid: {fmt_duration(row["AvgHåll"])}'
                    f'</div></div>',
                    unsafe_allow_html=True)

    # Combined table if both exist
    if not tagged_grade.empty and not tagged_strat.empty:
        both = filtered_ann[(filtered_ann['Strategi'] != '–') & (filtered_ann['Betyg'] != '–')]
        if not both.empty:
            st.markdown('<div class="section-header">STRATEGI × BETYG</div>', unsafe_allow_html=True)
            cross = both.groupby(['Strategi','Betyg']).agg(
                Trades=('Vinst ($)', 'count'),
                AvgPct=('Vinst %', 'mean'),
                WinRate=('Vinst ($)', lambda x: (x>0).sum()/len(x)*100),
            ).reset_index()
            cross['AvgPct']  = cross['AvgPct'].round(1)
            cross['WinRate'] = cross['WinRate'].round(1)
            st.dataframe(cross.rename(columns={'AvgPct':'Avg %','WinRate':'Win%'}),
                         width='stretch', hide_index=True)