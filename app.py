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
GRADES     = ["–", "A — Jättebra", "B — Bra", "C — Dålig"]
ANNOTATIONS_FILE = os.path.join(base_dir, "annotations.json")

# --- PAGE ---
st.set_page_config(page_title="Trading Journal", page_icon="📈", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;700;800&display=swap');
:root{--bg:#0a0a0f;--surface:#111118;--border:#1e1e2e;--accent:#00ff88;--accent2:#ff3366;--text:#e8e8f0;--muted:#555570;--card:#13131c;}
html,body,.stApp{background-color:var(--bg)!important;color:var(--text)!important;font-family:'Syne',sans-serif;}
.stApp>header{background:transparent!important;}
[data-testid="stSidebar"]{background:var(--surface)!important;border-right:1px solid var(--border)!important;}
[data-testid="stSidebar"] *{color:var(--text)!important;}
#MainMenu,footer,header{visibility:hidden;}
.block-container{padding:2rem!important;max-width:100%!important;}
.metric-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.2rem;text-align:center;}
.metric-card:hover{border-color:var(--accent);}
.metric-label{font-family:'Space Mono',monospace;font-size:0.65rem;letter-spacing:0.15em;color:var(--muted);text-transform:uppercase;margin-bottom:0.4rem;}
.metric-value{font-family:'Space Mono',monospace;font-size:1.5rem;font-weight:700;line-height:1.1;}
.metric-sub{font-family:'Space Mono',monospace;font-size:0.7rem;color:var(--muted);margin-top:0.2rem;}
.positive{color:#00ff88;}.negative{color:#ff3366;}.neutral{color:var(--text);}
.app-header{display:flex;align-items:baseline;gap:1rem;margin-bottom:2rem;border-bottom:1px solid var(--border);padding-bottom:1.5rem;}
.app-title{font-family:'Syne',sans-serif;font-weight:800;font-size:2rem;color:var(--text);letter-spacing:-0.02em;}
.app-subtitle{font-family:'Space Mono',monospace;font-size:0.75rem;color:var(--muted);letter-spacing:0.1em;}
.section-header{font-family:'Space Mono',monospace;font-size:0.7rem;letter-spacing:0.2em;color:var(--muted);text-transform:uppercase;margin:1.5rem 0 1rem 0;padding-bottom:0.5rem;border-bottom:1px solid var(--border);}
.live-dot{display:inline-block;width:8px;height:8px;background:var(--accent);border-radius:50%;margin-right:6px;animation:pulse 1.5s infinite;}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:0.4;transform:scale(0.8)}}
.stButton>button{background:transparent!important;border:1px solid var(--accent)!important;color:var(--accent)!important;font-family:'Space Mono',monospace!important;font-size:0.75rem!important;letter-spacing:0.1em!important;border-radius:6px!important;}
.stButton>button:hover{background:var(--accent)!important;color:var(--bg)!important;}
.stTabs [data-baseweb="tab-list"]{background:transparent!important;border-bottom:1px solid var(--border)!important;}
.stTabs [data-baseweb="tab"]{background:transparent!important;color:var(--muted)!important;font-family:'Space Mono',monospace!important;font-size:0.72rem!important;letter-spacing:0.1em!important;border:none!important;}
.stTabs [aria-selected="true"]{color:var(--accent)!important;border-bottom:2px solid var(--accent)!important;}
</style>
""", unsafe_allow_html=True)


# --- ANNOTATIONS ---
def load_annotations():
    if 'annotations' not in st.session_state:
        try:
            st.session_state.annotations = json.loads(Path(ANNOTATIONS_FILE).read_text())
        except:
            st.session_state.annotations = {}
    return st.session_state.annotations

def save_annotations():
    try:
        Path(ANNOTATIONS_FILE).write_text(json.dumps(st.session_state.annotations, indent=2))
    except: pass

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
        start = (pd.to_datetime(start_date) - timedelta(days=15)).strftime('%Y-%m-%d')
        end   = (pd.to_datetime(end_date)   + timedelta(days=10)).strftime('%Y-%m-%d')
        df = yf.download(ticker, start=start, end=end, progress=False)
        if df.empty: return None
        # yfinance returns MultiIndex columns for single ticker, flatten
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        return df
    except: return None


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
        })
    df = pd.DataFrame(rows).sort_values('Tidsstämpel').reset_index(drop=True)
    valid_trades = []

    for symbol, group in df.groupby('Symbol'):
        long_fifo, short_fifo, position = [], [], 0.0
        entry_time, entry_date = None, None

        for _, row in group.iterrows():
            qty, price, side = abs(float(row['Antal'])), abs(float(row['Pris'])), row['Side']
            ts, datum = row['Tidsstämpel'], row['Datum']
            if math.isnan(price) or qty == 0 or price == 0: continue

            if abs(position) < 0.01 and qty > 0:
                entry_time, entry_date = ts, datum

            if side == 'BUY':
                if position < -0.01:
                    remaining, pnl, cost = qty, 0.0, 0.0
                    while remaining > 0.01 and short_fifo:
                        oq, op = short_fifo[0]; m = min(remaining, oq)
                        pnl += m*(op-price); cost += m*op
                        remaining -= m; oq -= m
                        if oq < 0.01: short_fifo.pop(0)
                        else: short_fifo[0] = (oq, op)
                    pct = (pnl/cost*100) if cost > 0 else 0
                    dur = round((ts - entry_time).total_seconds()/60) if entry_time else None
                    valid_trades.append({'Ticker':symbol, 'Vinst ($)':round(pnl,2), 'Vinst %':round(pct,1),
                        'Riktning':'SHORT', 'Datum':datum, 'Entry Datum':entry_date or datum,
                        'Tidsstämpel':ts, 'Hålltid (min)':dur})
                    if remaining > 0.01: long_fifo.append((remaining, price))
                    if abs(position+qty) < 0.01: entry_time = entry_date = None
                else:
                    if abs(position) < 0.01: entry_time, entry_date = ts, datum
                    long_fifo.append((qty, price))
                position += qty
            else:
                if position > 0.01:
                    remaining, pnl, cost = qty, 0.0, 0.0
                    while remaining > 0.01 and long_fifo:
                        oq, op = long_fifo[0]; m = min(remaining, oq)
                        pnl += m*(price-op); cost += m*op
                        remaining -= m; oq -= m
                        if oq < 0.01: long_fifo.pop(0)
                        else: long_fifo[0] = (oq, op)
                    pct = (pnl/cost*100) if cost > 0 else 0
                    dur = round((ts - entry_time).total_seconds()/60) if entry_time else None
                    valid_trades.append({'Ticker':symbol, 'Vinst ($)':round(pnl,2), 'Vinst %':round(pct,1),
                        'Riktning':'LONG', 'Datum':datum, 'Entry Datum':entry_date or datum,
                        'Tidsstämpel':ts, 'Hålltid (min)':dur})
                    if remaining > 0.01: short_fifo.append((remaining, price))
                    if abs(position-qty) < 0.01: entry_time = entry_date = None
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

# --- SIDEBAR ---
with st.sidebar:
    st.markdown('<div class="section-header">KONTROLL</div>', unsafe_allow_html=True)
    if st.button("↻  UPPDATERA DATA"):
        st.cache_data.clear(); st.rerun()
    st.markdown('<div class="section-header">FILTER</div>', unsafe_allow_html=True)
    date_from = st.date_input("Från datum", value=datetime(2026, 1, 1))
    date_to   = st.date_input("Till datum",  value=datetime.today())
    st.markdown('<div class="section-header">RIKTNING</div>', unsafe_allow_html=True)
    show_long  = st.checkbox("LONG",  value=True)
    show_short = st.checkbox("SHORT", value=True)
    st.markdown('<div class="section-header">STRATEGI</div>', unsafe_allow_html=True)
    strat_filter = st.selectbox("Visa strategi", ["Alla"] + STRATEGIES[1:])
    st.markdown('<div class="section-header">INFO</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-family:Space Mono,monospace;font-size:0.65rem;color:#555570;line-height:1.8;">KONTO: {ACCOUNT_ID or "–"}<br>UPPDATERAD: {datetime.now().strftime("%H:%M:%S")}</div>', unsafe_allow_html=True)


# --- LOAD ---
annotations = load_annotations()
with st.spinner("Hämtar data..."):
    all_trades = fetch_all_trades()
    pnl_data   = fetch_pnl()

if not all_trades:
    st.error("Inga trades. Kontrollera API-nycklar."); st.stop()

res_df = compute_fifo(all_trades)

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
    cols = st.columns(8)
    for col, (label, val, fmt) in zip(cols, [
        ("NETTO P/L", total_pnl, "dollar"), ("WIN RATE", win_rate, "pct"), ("TRADES", total, "int"),
        ("AVG VINST $", avg_win_dollar, "dollar"), ("AVG FÖRLUST $", avg_loss_dollar, "dollar"),
        ("AVG VINST %", avg_win_pct, "pct"), ("AVG FÖRLUST %", avg_loss_pct, "pct"), ("RISK/REWARD", rr, "x"),
    ]):
        with col: st.markdown(mcard(label, val, fmt), unsafe_allow_html=True)

    st.markdown('<div class="section-header">GENOMSNITTLIG HÅLLTID</div>', unsafe_allow_html=True)
    t1, t2, t3 = st.columns(3)
    with t1: st.markdown(mcard("VINNANDE", avg_win_time or 0, "time"), unsafe_allow_html=True)
    with t2: st.markdown(mcard("FÖRLORANDE", avg_loss_time or 0, "time"), unsafe_allow_html=True)
    all_time = filtered['Hålltid (min)'].dropna().mean()
    with t3: st.markdown(mcard("ALLA", all_time or 0, "time"), unsafe_allow_html=True)


# --- TABS ---
st.markdown('<div class="section-header">ANALYS</div>', unsafe_allow_html=True)
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["P/L KURVA", "PER TICKER", "MÅNADER", "TRADE DETALJ", "ALLA TRADES", "RAW DATA"])


with tab1:
    if not filtered.empty:
        daily = filtered.groupby('Datum')['Vinst ($)'].sum().reset_index().sort_values('Datum')
        daily['Kumulativ'] = daily['Vinst ($)'].cumsum()
        col_a, col_b = st.columns([2, 1])
        with col_a:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=daily['Datum'], y=daily['Kumulativ'],
                fill='tozeroy', fillcolor='rgba(0,255,136,0.05)',
                line=dict(color='#00ff88', width=2), hovertemplate='%{x}<br>$%{y:,.0f}<extra></extra>'))
            fig.add_hline(y=0, line_dash='dot', line_color='#333344')
            fig.update_layout(**PLOTLY_LAYOUT, height=300, title='Kumulativ P/L')
            st.plotly_chart(fig, width='stretch')
        with col_b:
            colors = ['#00ff88' if v > 0 else '#ff3366' for v in daily['Vinst ($)']]
            fig2 = go.Figure(go.Bar(x=daily['Datum'], y=daily['Vinst ($)'],
                marker_color=colors, hovertemplate='%{x}<br>$%{y:,.0f}<extra></extra>'))
            fig2.update_layout(**PLOTLY_LAYOUT, height=300, title='Daglig P/L')
            st.plotly_chart(fig2, width='stretch')
    else: st.info("Inga trades i valt intervall.")


with tab2:
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


with tab3:
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

        colors = ['#00ff88' if v > 0 else '#ff3366' for v in by_month['PnL']]
        fig4 = go.Figure(go.Bar(x=by_month['Månad'], y=by_month['PnL'], marker_color=colors,
            hovertemplate='%{x}<br>$%{y:,.0f}<extra></extra>',
            text=[f"${v:+,.0f}" for v in by_month['PnL']], textposition='outside',
            textfont=dict(color=['#00ff88' if v > 0 else '#ff3366' for v in by_month['PnL']])))
        fig4.update_layout(**PLOTLY_LAYOUT, height=280, title='Månadsvis P/L', xaxis_type='category')
        st.plotly_chart(fig4, width='stretch')
        st.dataframe(by_month[['Månad','Trades','Vinster','Förluster','Win%','PnL','AvgVinstPct','AvgFörlustPct']]
            .rename(columns={'PnL':'P/L ($)','AvgVinstPct':'Avg Vinst %','AvgFörlustPct':'Avg Förlust %'}),
            width='stretch', hide_index=True)
    else: st.info("Inga trades i valt intervall.")


with tab4:
    if not filtered.empty:
        st.markdown('<div class="section-header">VÄLJ TRADE</div>', unsafe_allow_html=True)

        trade_options = []
        for _, r in filtered.sort_values('Datum', ascending=False).iterrows():
            pnl_sign = "✅" if r['Vinst ($)'] > 0 else "❌"
            strat_tag = f" [{r['Strategi']}]" if r['Strategi'] != '–' else ""
            grade_tag = f" ({r['Betyg'][0]})" if r['Betyg'] != '–' else ""
            trade_options.append(f"{pnl_sign} {r['Ticker']}  {r['Entry Datum']} → {r['Datum']}  ${r['Vinst ($)']:+,.0f}  {r['Riktning']}{strat_tag}{grade_tag}")

        selected_idx = st.selectbox("Trade", range(len(trade_options)),
            format_func=lambda i: trade_options[i], label_visibility="collapsed")
        trade = filtered.sort_values('Datum', ascending=False).iloc[selected_idx]
        tk = trade_key(trade)

        # Strategy + Grade
        col_s, col_g = st.columns(2)
        with col_s:
            curr_strat = annotations.get(tk, {}).get('strategy', '–')
            new_strat = st.selectbox("Strategi", STRATEGIES,
                index=STRATEGIES.index(curr_strat) if curr_strat in STRATEGIES else 0,
                key=f"strat_{tk}")
        with col_g:
            curr_grade = annotations.get(tk, {}).get('grade', '–')
            new_grade = st.selectbox("Betyg", GRADES,
                index=GRADES.index(curr_grade) if curr_grade in GRADES else 0,
                key=f"grade_{tk}")

        if new_strat != curr_strat or new_grade != curr_grade:
            if tk not in st.session_state.annotations:
                st.session_state.annotations[tk] = {}
            st.session_state.annotations[tk]['strategy'] = new_strat
            st.session_state.annotations[tk]['grade'] = new_grade
            save_annotations()

        # Trade info
        col_i1, col_i2, col_i3, col_i4 = st.columns(4)
        with col_i1: st.markdown(mcard("P/L", trade['Vinst ($)'], "dollar"), unsafe_allow_html=True)
        with col_i2: st.markdown(mcard("VINST %", trade['Vinst %'], "pct"), unsafe_allow_html=True)
        with col_i3: st.markdown(mcard("RIKTNING", 0, "raw", sub=trade['Riktning']), unsafe_allow_html=True)
        with col_i4: st.markdown(mcard("HÅLLTID", trade.get('Hålltid (min)') or 0, "time"), unsafe_allow_html=True)

        # Chart
        st.markdown('<div class="section-header">KURSGRAF</div>', unsafe_allow_html=True)
        with st.spinner(f"Hämtar kursdata för {trade['Ticker']}..."):
            chart_df = fetch_chart_data(trade['Ticker'], trade['Entry Datum'], trade['Datum'])

        if chart_df is not None and not chart_df.empty:
            fig_chart = go.Figure()
            fig_chart.add_trace(go.Candlestick(
                x=chart_df['Date'], open=chart_df['Open'], high=chart_df['High'],
                low=chart_df['Low'], close=chart_df['Close'],
                increasing_line_color='#00ff88', decreasing_line_color='#ff3366',
                increasing_fillcolor='#00ff88', decreasing_fillcolor='#ff3366',
                name='Pris'))

            # Entry marker
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
                    showlegend=False))
            if not exit_row.empty:
                fig_chart.add_trace(go.Scatter(
                    x=[exit_row['Date'].iloc[0]], y=[float(exit_row['High'].iloc[0]) * 1.02],
                    mode='markers+text', marker=dict(symbol='triangle-down', size=16, color=exit_color),
                    text=['EXIT'], textposition='top center', textfont=dict(color=exit_color, size=10),
                    showlegend=False))

            fig_chart.update_layout(**PLOTLY_LAYOUT, height=400,
                title=f"{trade['Ticker']} — {trade['Entry Datum']} → {trade['Datum']}",
                xaxis_rangeslider_visible=False)
            st.plotly_chart(fig_chart, width='stretch')
        else:
            st.warning(f"Kunde inte hämta kursdata för {trade['Ticker']}. Kontrollera att yfinance är installerat.")

        # Notes
        curr_notes = annotations.get(tk, {}).get('notes', '')
        new_notes = st.text_area("Anteckningar", value=curr_notes, key=f"notes_{tk}", height=80,
                                  placeholder="Skriv anteckningar om denna trade...")
        if new_notes != curr_notes:
            if tk not in st.session_state.annotations: st.session_state.annotations[tk] = {}
            st.session_state.annotations[tk]['notes'] = new_notes
            save_annotations()
    else:
        st.info("Inga trades i valt intervall.")


with tab5:
    if not filtered.empty:
        display = filtered[['Datum','Entry Datum','Ticker','Riktning','Vinst ($)','Vinst %','Strategi','Betyg','Hålltid (min)']].copy()
        display['Hålltid'] = display['Hålltid (min)'].apply(fmt_duration)
        display = display.drop(columns=['Hålltid (min)']).sort_values('Datum', ascending=False)
        def color_pnl(val):
            if isinstance(val, (int, float)):
                return f'color: {"#00ff88" if val > 0 else "#ff3366" if val < 0 else "#888899"};'
            return ''
        styled = display.style.map(color_pnl, subset=['Vinst ($)', 'Vinst %'])\
                              .format({'Vinst ($)': '{:+,.2f}', 'Vinst %': '{:+.1f}%'})
        st.dataframe(styled, width='stretch', hide_index=True, height=500)
    else: st.info("Inga trades i valt intervall.")


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


# --- STRATEGY STATS (bottom) ---
if not filtered.empty:
    tagged = filtered[filtered['Strategi'] != '–']
    if not tagged.empty:
        st.markdown('<div class="section-header">STATISTIK PER STRATEGI</div>', unsafe_allow_html=True)
        by_strat = tagged.groupby('Strategi').agg(
            Trades=('Vinst ($)', 'count'), PnL=('Vinst ($)', 'sum'),
            WinRate=('Vinst ($)', lambda x: (x>0).sum()/len(x)*100),
            AvgPct=('Vinst %', 'mean'),
        ).reset_index()
        by_strat['PnL']     = by_strat['PnL'].round(0)
        by_strat['WinRate'] = by_strat['WinRate'].round(1)
        by_strat['AvgPct']  = by_strat['AvgPct'].round(1)

        cols = st.columns(len(by_strat))
        for col, (_, row) in zip(cols, by_strat.iterrows()):
            with col:
                st.markdown(mcard(row['Strategi'].split("/")[0].strip().upper(),
                    row['PnL'], "dollar",
                    sub=f"{int(row['Trades'])} trades | {row['WinRate']:.0f}% win | avg {row['AvgPct']:+.0f}%"),
                    unsafe_allow_html=True)