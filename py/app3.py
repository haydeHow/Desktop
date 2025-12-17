from flask import Flask, request, jsonify, Response
import time
import requests
from datetime import date
import yfinance as yf

app = Flask(__name__)

# ==============================
# STOCK CACHE
# ==============================

CACHE = {}  # { "AAPL": (timestamp, data) }
CACHE_TTL_SECONDS = 300  # 5 minutes


def fetch_stock_yf(symbol: str) -> dict:
    t = yf.Ticker(symbol)
    fi = t.fast_info or {}

    price = fi.get("lastPrice")
    if price is None:
        raise RuntimeError("No price data")

    try:
        hist = t.history(period="6mo", interval="1d")
        closes = hist["Close"].dropna().tolist()
    except Exception:
        closes = []

    def pct_from_past(past):
        return None if past is None else (price - past) / past * 100.0

    day = pct_from_past(closes[-2]) if len(closes) >= 2 else None
    mo = pct_from_past(closes[-22]) if len(closes) >= 22 else None
    mo6 = pct_from_past(closes[0]) if len(closes) >= 126 else None

    low = fi.get("yearLow")
    high = fi.get("yearHigh")

    return {
        "price": f"{price:.2f}",
        "day": day,
        "mo": mo,
        "mo6": mo6,
        "low": f"{low:.2f}" if low is not None else None,
        "high": f"{high:.2f}" if high is not None else None,
        "volume": fi.get("lastVolume"),
        "market_open": fi.get("marketState") == "REGULAR",
    }


@app.get("/api/stock")
def api_stock():
    symbol = (request.args.get("symbol") or "").strip().upper()
    if not symbol:
        return jsonify({"error": "Missing symbol"}), 400

    now = time.time()
    cached = CACHE.get(symbol)
    if cached and (now - cached[0] < CACHE_TTL_SECONDS):
        return jsonify(cached[1])

    try:
        data = fetch_stock_yf(symbol)
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    CACHE[symbol] = (now, data)
    return jsonify(data)


# ==============================
# WIKIPEDIA "ON THIS DAY"
# ==============================

WIKI_CACHE = {}
WIKI_TTL = 86400  # 1 day


def is_calm(text: str) -> bool:
    bad = ("war", "killed", "attack", "bomb", "battle")
    t = text.lower()
    return not any(w in t for w in bad)


def fetch_wikipedia_event() -> str:
    today = date.today()
    key = today.strftime("%m-%d")
    now = time.time()

    cached = WIKI_CACHE.get(key)
    if cached and (now - cached[0] < WIKI_TTL):
        return cached[1]

    m = today.strftime("%m")
    d = today.strftime("%d")

    url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{m}/{d}"

    try:
        r = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "dashboard/1.0"}
        )
        r.raise_for_status()

        data = r.json()
        events = data.get("events", [])

        event = next(
            (e for e in events if e.get("text") and is_calm(e["text"])),
            events[0]
        )

        text = f'in {event["year"]}, {event["text"]}'
        text = text[:1].upper() + text[1:]

    except Exception:
        text = "no data today."

    WIKI_CACHE[key] = (now, text)
    return text


@app.get("/api/wiki")
def api_wiki():
    return fetch_wikipedia_event()


# ==============================
# WEATHER (NEW — SAFE ADDITION)
# ==============================

WEATHER_CACHE = {}
WEATHER_TTL = 1800  # 30 minutes


def fetch_weather() -> str:
    key = "today"
    now = time.time()

    cached = WEATHER_CACHE.get(key)
    if cached and (now - cached[0] < WEATHER_TTL):
        return cached[1]

    # CHANGE THESE IF YOU WANT A DIFFERENT LOCATION
    lat = 40.7128
    lon = -74.0060

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,weathercode"
    )

    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()

        current = data.get("current", {})
        temp = current.get("temperature_2m")
        code = current.get("weathercode")

        CONDITIONS = {
            0: "clear",
            1: "mostly clear",
            2: "partly cloudy",
            3: "overcast",
            45: "foggy",
            61: "light rain",
            63: "rain",
            71: "snow",
        }

        condition = CONDITIONS.get(code, "unknown conditions")
        text = f"{condition}, {temp}°C"
        text = text[:1].upper() + text[1:]

    except Exception:
        text = "Weather unavailable."

    WEATHER_CACHE[key] = (now, text)
    return text


@app.get("/api/weather")
def api_weather():
    return fetch_weather()



# ==============================
# MAIN PAGE
# ==============================

@app.get("/")
def index():
    html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>daily dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">

<style>
:root {
  --bg: #1e1e1e;
  --panel: #252525;
  --border: #3a3a3a;
  --fg: #e6e6e6;
  --muted: #a0a0a0;
  --accent: #cfcfcf;
  --pos: #6fcf97;
  --neg: #eb5757;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 16px;
  background: var(--bg);
  color: var(--fg);
  font: 15px/1.5 sans-serif;
}
.wrap { max-width: 900px; margin: 0 auto; }
header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 16px;
}
header h1 { font-size: 18px; margin: 0; }
.time { font-size: 22px; }
.date { color: var(--muted); font-size: 13px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.panel { background: var(--panel); border: 1px solid var(--border); padding: 12px; }
.panel.full { grid-column: 1 / -1; }
.panel h2 {
  margin: 0 0 8px;
  font-size: 14px;
  color: var(--accent);
  border-bottom: 1px solid var(--border);
}
table { width: 100%; border-collapse: collapse; margin-top: 6px; }
th, td {
  border-bottom: 1px solid var(--border);
  padding: 4px 2px;
  text-align: right;
  font-size: 13px;
}
th:first-child, td:first-child { text-align: left; }
.pos { color: var(--pos); }
.neg { color: var(--neg); }
.not-owned { opacity: 0.6; }
</style>
</head>

<body>
<div class="wrap">

<header>
  <h1>steven's dashboard</h1>
  <div>
    <div class="time" id="time"></div>
    <div class="date" id="date"></div>
  </div>
</header>

<div class="grid">



  <div class="panel">
    <h2>forecast</h2>
    <div id="weather">loading…</div>
  </div>

  <div class="panel">
    <h2>on this day</h2>
    <div id="history">loading…</div>
  </div>

  <div class="panel full">
    <h2>
      stocks
      <span id="marketStatus" style="float:right;color:var(--muted)"></span>
    </h2>

    <input id="tickers" value="AAPL,MSFT,SPY" size="30">
    <button id="loadBtn">load</button>

    <table>
      <thead>
        <tr>
          <th>ticker</th>
          <th>price</th>
          <th>day</th>
          <th>1 mo</th>
          <th>6 mo</th>
          <th>since bought</th>
          <th>low / high</th>
          <th>vol</th>
        </tr>
      </thead>
      <tbody id="stockRows"></tbody>
    </table>
  </div>

</div>
</div>

<script>
const timeEl = document.getElementById("time");
const dateEl = document.getElementById("date");
const historyEl = document.getElementById("history");
const tickersEl = document.getElementById("tickers");
const stockRowsEl = document.getElementById("stockRows");
const marketStatusEl = document.getElementById("marketStatus");
const weatherEl = document.getElementById("weather");


/* ==============================
   PERSONAL COST BASIS
   ============================== */
const COST_BASIS = {
  AAPL: 145.23,
  MSFT: 312.10,
  SPY: 430.00,
};

function updateTime() {
  const n = new Date();
  timeEl.textContent = n.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"});
  dateEl.textContent = n.toLocaleDateString(undefined,{weekday:"long",year:"numeric",month:"long",day:"numeric"});
}
updateTime();
setInterval(updateTime, 60000);

async function loadWiki() {
  try {
    const r = await fetch("/api/wiki");
    historyEl.textContent = await r.text();
  } catch {
    historyEl.textContent = "no data today.";
  }
}
loadWiki();

function fmtPct(v){
  if(v==null) return "—";
  return `<span class="${v>=0?"pos":"neg"}">${v.toFixed(2)}%</span>`;
}
function fmtNum(v){
  if(v==null) return "—";
  if(v>=1e9) return (v/1e9).toFixed(1)+"B";
  if(v>=1e6) return (v/1e6).toFixed(1)+"M";
  if(v>=1e3) return (v/1e3).toFixed(1)+"K";
  return v.toLocaleString();
}
function sinceBoughtPct(price, basis){
  if(price==null || basis==null) return null;
  return ((price - basis) / basis) * 100;
}

async function loadStocks(){
  stockRowsEl.innerHTML="";
  marketStatusEl.textContent="";
  const syms = tickersEl.value.split(",").map(s=>s.trim().toUpperCase()).filter(Boolean);

  for(const sym of syms){
    const tr=document.createElement("tr");
    tr.innerHTML=`<td>${sym}</td><td colspan="7">loading…</td>`;
    stockRowsEl.appendChild(tr);

    try{
      const r=await fetch(`/api/stock?symbol=${sym}`);
      const s=await r.json();

      const basis = COST_BASIS[sym];
      const since = sinceBoughtPct(Number(s.price), basis);

      if (!basis) tr.classList.add("not-owned");
      if (since != null && since > 0) tr.style.fontWeight = "600";

      if(s.market_open!=null && !marketStatusEl.textContent)
        marketStatusEl.textContent = s.market_open ? "market open" : "market closed";

      tr.innerHTML=`
        <td>${sym}</td>
        <td>$${s.price ?? "—"}</td>
        <td>${fmtPct(s.day)}</td>
        <td>${fmtPct(s.mo)}</td>
        <td>${fmtPct(s.mo6)}</td>
        <td>${basis ? `${fmtPct(since)} <span style="color:var(--muted)">(@ ${basis})</span>` : "—"}</td>
        <td>${s.low && s.high ? `$${s.low} – $${s.high}` : "—"}</td>
        <td>${fmtNum(s.volume)}</td>`;
    }catch{
      tr.innerHTML=`<td>${sym}</td><td colspan="7">error</td>`;
    }
  }
}
document.getElementById("loadBtn").onclick = loadStocks;


async function loadWeather() {
  try {
    const r = await fetch("/api/weather");
    weatherEl.textContent = await r.text();
  } catch {
    weatherEl.textContent = "Weather unavailable.";
  }
}
loadWeather();
</script>

</body>
</html>"""
    return Response(html, mimetype="text/html")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
