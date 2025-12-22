from flask import Flask, request, jsonify, Response
import time
import requests
from datetime import date, datetime, timedelta
import yfinance as yf

app = Flask(__name__)

# ==============================
# STOCK CACHE
# ==============================

CACHE = {}  # { "AAPL": (timestamp, data) }
CACHE_TTL_SECONDS = 300  # 5 minutes

# Cache for historical basis lookups: { ("AAPL","2024-01-02"): (timestamp, basis_float_or_none) }
BASIS_CACHE = {}
BASIS_CACHE_TTL_SECONDS = 86400  # 1 day

def fetch_stock_yf(symbol: str) -> dict:
    t = yf.Ticker(symbol)
    fi = t.fast_info or {}

    price = fi.get("lastPrice")
    if price is None:
        raise RuntimeError("No price data")

    try:
        # Fetch enough data for 1 year comparisons
        hist = t.history(period="1y", interval="1d")
        closes = hist["Close"].dropna().tolist()
    except Exception:
        closes = []

    def pct_from_past(past):
        return None if past is None else (price - past) / past * 100.0

    day = pct_from_past(closes[-2]) if len(closes) >= 2 else None
    mo3 = pct_from_past(closes[-63]) if len(closes) >= 63 else None
    yr = pct_from_past(closes[0]) if len(closes) >= 2 else None


    low = fi.get("yearLow")
    high = fi.get("yearHigh")

    return {
        "price": f"{price:.2f}",
        "day": day,
        "mo3": mo3,   # ← NEW
        "yr": yr,     # ← NEW
        "low": f"{low:.2f}" if low is not None else None,
        "high": f"{high:.2f}" if high is not None else None,
        "volume": fi.get("lastVolume"),
        "market_open": fi.get("marketState") == "REGULAR",
    }



def fetch_basis_on_date(symbol: str, buy_date_str: str):
    """
    Returns the Close price for `symbol` on buy_date_str (YYYY-MM-DD), or None.
    Uses start=buy_date and end=buy_date+1 day to capture that day's bar.
    """
    try:
        d0 = datetime.strptime(buy_date_str, "%Y-%m-%d").date()
    except Exception:
        return None

    key = (symbol, buy_date_str)
    now = time.time()

    cached = BASIS_CACHE.get(key)
    if cached and (now - cached[0] < BASIS_CACHE_TTL_SECONDS):
        return cached[1]

    try:
        t = yf.Ticker(symbol)
        d1 = d0 + timedelta(days=1)
        hist = t.history(start=d0.isoformat(), end=d1.isoformat(), interval="1d")
        if hist is None or hist.empty:
            basis = None
        else:
            basis = float(hist["Close"].iloc[0])
    except Exception:
        basis = None

    BASIS_CACHE[key] = (now, basis)
    return basis


@app.get("/api/stock")
def api_stock():
    symbol = (request.args.get("symbol") or "").strip().upper()
    buy_date_str = (request.args.get("buy_date") or "").strip()

    if not symbol:
        return jsonify({"error": "Missing symbol"}), 400

    now = time.time()
    cached = CACHE.get(symbol)
    if cached and (now - cached[0] < CACHE_TTL_SECONDS):
        data = dict(cached[1])  # copy so we can safely add basis
    else:
        try:
            data = fetch_stock_yf(symbol)
        except Exception as e:
            return jsonify({"error": str(e)}), 502
        CACHE[symbol] = (now, data)
        data = dict(data)

    # Optional: add basis if buy_date provided
    if buy_date_str:
        data["basis"] = fetch_basis_on_date(symbol, buy_date_str)
    else:
        data["basis"] = None

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
    html = """

    <!doctype html>
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
input.sharesInput, input.dateInput {
  background: #1e1e1e;
  color: #e6e6e6;
  border: 1px solid #3a3a3a;
}
input.sharesInput { width: 60px; }
input.dateInput { width: 140px; }
</style>
</head>

<body>
<div class="wrap">

<header>
  <h1>Steven's Dashboard</h1>
  <div>
    <div class="time" id="time"></div>
    <div class="date" id="date"></div>
  </div>
</header>

<div class="grid">

  <div class="panel">
    <h2>Forecast</h2>
    <div id="weather">loading…</div>
  </div>

  <div class="panel">
    <h2>On This Day</h2>
    <div id="history">loading…</div>
  </div>

  <div class="panel full">
    <h2>Profit</h2>
    <div id="profitSummary">Load stocks to see profit</div>
  </div>

  <div class="panel full">
    <h2>
      Stocks
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
          <th>3 mo</th>
          <th>1 yr</th>
          <th>low / high</th>
          <th>vol</th>
          <th>shares</th>
          <th>bought</th>
          <th>since bought</th>
        </tr>
      </thead>
      <tbody id="stockRows"></tbody>
    </table>
  </div>

</div>
</div>

<script>


/* ---- ELEMENTS ---- */
const timeEl = document.getElementById("time");
const dateEl = document.getElementById("date");
const historyEl = document.getElementById("history");
const weatherEl = document.getElementById("weather");
const profitEl = document.getElementById("profitSummary");

const tickersEl = document.getElementById("tickers");
const stockRowsEl = document.getElementById("stockRows");
const marketStatusEl = document.getElementById("marketStatus");

/* ---- SHARES + BUY DATE (persisted) ---- */
function getShares(sym) {
  return Number(localStorage.getItem("shares:" + sym)) || 0;
}
function setShares(sym, v) {
  localStorage.setItem("shares:" + sym, v);
}

function getBuyDate(sym) {
  return localStorage.getItem("buydate:" + sym) || "";
}
function setBuyDate(sym, v) {
  localStorage.setItem("buydate:" + sym, v);
}

document.addEventListener("input", (e) => {
  if (e.target.classList.contains("sharesInput")) {
    setShares(e.target.dataset.sym, Number(e.target.value) || 0);
  }
  if (e.target.classList.contains("dateInput")) {
    setBuyDate(e.target.dataset.sym, e.target.value || "");
  }
});

/* ---- TIME ---- */
function updateTime() {
  const n = new Date();
  timeEl.textContent = n.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"});
  dateEl.textContent = n.toLocaleDateString(undefined,{
    weekday:"long",year:"numeric",month:"long",day:"numeric"
  });
}

/* ---- LOADERS ---- */
async function loadWiki() {
  try {
    const r = await fetch("/api/wiki");
    historyEl.textContent = await r.text();
  } catch {
    historyEl.textContent = "no data today.";
  }
}

async function loadWeather() {
  try {
    const r = await fetch("/api/weather");
    weatherEl.textContent = await r.text();
  } catch {
    weatherEl.textContent = "Weather unavailable.";
  }
}

/* ---- FORMATTERS ---- */
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

/* ---- STOCKS + PROFIT ---- */
async function loadStocks(){
  stockRowsEl.innerHTML="";
  marketStatusEl.textContent="";

  let totalInvested = 0;
  let totalValue = 0;

  const syms = tickersEl.value.split(",").map(s=>s.trim().toUpperCase()).filter(Boolean);

  for(const sym of syms){
    const tr=document.createElement("tr");
    tr.innerHTML=`<td>${sym}</td><td colspan="9">loading…</td>`;
    stockRowsEl.appendChild(tr);

    try{
      const buyDate = getBuyDate(sym);
      const url = buyDate
        ? `/api/stock?symbol=${encodeURIComponent(sym)}&buy_date=${encodeURIComponent(buyDate)}`
        : `/api/stock?symbol=${encodeURIComponent(sym)}`;

      const r=await fetch(url);
      const s=await r.json();

      const price = s.price != null ? Number(s.price) : null;
      const basis = s.basis != null ? Number(s.basis) : null;
      const shares = getShares(sym);
      const since = sinceBoughtPct(price, basis);

      if (basis != null && price != null && shares > 0) {
        totalInvested += basis * shares;
        totalValue += price * shares;
      }

      if (!(shares > 0 && basis != null)) tr.classList.add("not-owned");

      if(s.market_open!=null && !marketStatusEl.textContent)
        marketStatusEl.textContent = s.market_open ? "Market Open" : "Market Closed";

      tr.innerHTML = `
        <td>${sym}</td>
        <td>$${s.price ?? "—"}</td>
        <td>${fmtPct(s.day)}</td>
        <td>${fmtPct(s.mo3)}</td>
        <td>${fmtPct(s.yr)}</td>
        <td>${s.low && s.high ? `$${s.low} – $${s.high}` : "—"}</td>
        <td>${fmtNum(s.volume)}</td>
        <td>
          <input type="number" min="0" step="1"
            class="sharesInput" data-sym="${sym}" value="${shares}">
        </td>
        <td>
          <input type="date"
            class="dateInput" data-sym="${sym}" value="${buyDate}">
        </td>
        <td>${(shares > 0 && basis != null) ? fmtPct(since) : "—"}</td>
      `;
    }catch{
      tr.innerHTML=`<td>${sym}</td><td colspan="9">error</td>`;
    }
  }

  if (totalInvested > 0) {
    const profit = totalValue - totalInvested;
    const pct = (profit / totalInvested) * 100;
    profitEl.innerHTML = `
      Invested: $${totalInvested.toFixed(2)}<br>
      Value: $${totalValue.toFixed(2)}<br>
      <strong class="${profit>=0?"pos":"neg"}">
        ${profit>=0?"+":""}$${profit.toFixed(2)} (${pct.toFixed(2)}%)
      </strong>
    `;
  } else {
    profitEl.textContent = "No positions.";
  }
}
127.0.0.1 - - [17/Dec/2025 13:21:28] "GET / HTTP/1.1" 200 -
127.0.0.1 - - [17/Dec/2025 13:21:28] "GET /api/weather HTTP/1.1" 200 -
127.0.0.1 - - [17/Dec/2025 13:21:28] "GET /api/wiki HTTP/1.1" 200 -
$AAPL: possibly delisted; no price data found  (period=1y)
$AAPL: possibly delisted; no price data found  (period=5d)
127.0.0.1 - - [17/Dec/2025 13:21:29] "GET /api/stock?symbol=AAPL&buy_date=2001-03-28 HTTP/1.1" 502 -
$MSFT: possibly delisted; no price data found  (period=1y)
$MSFT: possibly delisted; no price data found  (period=5d)
127.0.0.1 - - [17/Dec/2025 13:21:30] "GET /api/stock?symbol=MSFT&buy_date=2001-03-30 HTTP/1.1" 502 -
$SPY: possibly delisted; no price data found  (period=1y)
$SPY: possibly delisted; no price data found  (period=5d)
127.0.0.1 - - [17/Dec/2025 13:21:30] "GET /api/stock?symbol=SPY&buy_date=2001-03-30 HTTP/1.1" 502 -
/* ---- INIT ---- */
updateTime();
setInterval(updateTime, 60000);
loadWiki();
loadWeather();
document.getElementById("loadBtn").onclick = loadStocks;

</script>

</body>
</html>

"""
    return Response(html, mimetype="text/html")



if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
