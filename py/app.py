from flask import Flask, request, jsonify, Response
import requests
import time

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finance.yahoo.com/",
}

# Simple in-memory cache: { "AAPL": (timestamp, data) }
CACHE = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


def pct(cur: float, past: float | None):
    if not past:
        return None
    return (cur - past) / past * 100.0


def fetch_yahoo_stock(symbol: str):
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?range=1y&interval=1d"
    )
    r = requests.get(url, headers=HEADERS, timeout=10)
    # Yahoo sometimes returns plain text like "Edge: Too Many Requests"
    # so try JSON but fail gracefully.
    try:
        j = r.json()
    except Exception:
        raise RuntimeError(f"Yahoo non-JSON response: {r.text[:120]}")

    result = (j.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError("No chart result")

    meta = result.get("meta") or {}
    cur = meta.get("regularMarketPrice")
    if cur is None:
        raise RuntimeError("Missing regularMarketPrice")

    quote0 = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = [x for x in (quote0.get("close") or []) if isinstance(x, (int, float))]

    def get_close_from_end(n_from_end: int):
        # n_from_end=1 => last element, 2 => second-last, etc.
        if len(closes) >= n_from_end:
            return closes[-n_from_end]
        return None

    # Approx trading-day offsets
    day_past = get_close_from_end(2)
    mo_past = get_close_from_end(22)   # ~1 month ago (21 trading days)
    yr_past = closes[0] if len(closes) > 252 else None

    return {
        "price": f"{cur:.2f}",
        "day": pct(cur, day_past),
        "mo": pct(cur, mo_past),
        "yr": pct(cur, yr_past),
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
        data = fetch_yahoo_stock(symbol)
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    CACHE[symbol] = (now, data)
    return jsonify(data)

from datetime import date

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

    try:
        r = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{m}/{d}",
            timeout=10,
        )
        events = r.json().get("events", [])

        event = next(
            (e for e in events if e.get("text") and is_calm(e["text"])),
            events[0] if events else None,
        )

        text = (
            f'in {event["year"]}, {event["text"]}'
            if event
            else "nothing recorded."
        )

    except Exception:
        text = "no data today."

    WIKI_CACHE[key] = (now, text)
    return text



@app.get("/")
def index():
    html = r"""<!doctype html>
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
  font: 15px/1.5 "DejaVu Sans","Liberation Sans",sans-serif;
}
.wrap { max-width: 900px; margin: 0 auto; }
header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 16px;
}
header h1 { font-size: 18px; font-weight: 600; margin: 0; }
header .datetime { text-align: right; }
.time { font-size: 22px; }
.date { color: var(--muted); font-size: 13px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.panel { background: var(--panel); border: 1px solid var(--border); padding: 12px; }
.panel.full { grid-column: 1 / -1; }
.panel h2 {
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--accent);
  border-bottom: 1px solid var(--border);
  padding-bottom: 4px;
}
.content { font-size: 14px; line-height: 1.5; }
button, input {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--fg);
  font: inherit;
  padding: 4px 6px;
}
button:hover { border-color: var(--accent); }
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
</style>
</head>

<body>
<div class="wrap">

<header>
  <h1>steven's dashboard</h1>
  <div class="datetime">
    <div class="time" id="time"></div>
    <div class="date" id="date"></div>
  </div>
</header>

<div class="grid">

  <div class="panel">
    <h2>forecast</h2>
    <div class="content">calm and clear, mild temperature</div>
  </div>

  <div class="panel">
    <h2>on this day</h2>
    <div class="content" id="history">loading…</div>
  </div>

  <div class="panel full">
    <h2>stocks</h2>
    <div class="content">
      <input id="tickers" value="AAPL,MSFT,SPY" size="30">
      <button id="loadBtn">load</button>

      <table>
        <thead>
          <tr>
            <th>ticker</th>
            <th>price</th>
            <th>day</th>
            <th>1 mo</th>
            <th>1 yr</th>
          </tr>
        </thead>
        <tbody id="stockRows"></tbody>
      </table>
    </div>
  </div>

</div>
</div>

<script>
/* elements (avoid relying on implicit globals) */
const timeEl = document.getElementById("time");
const dateEl = document.getElementById("date");
const historyEl = document.getElementById("history");
const tickersEl = document.getElementById("tickers");
const stockRowsEl = document.getElementById("stockRows");
const loadBtn = document.getElementById("loadBtn");
const audioEl = document.getElementById("audio");

/* ===== TIME ===== */
function updateTime() {
  const now = new Date();
  timeEl.textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  dateEl.textContent = now.toLocaleDateString(undefined, {
    weekday: "long", year: "numeric", month: "long", day: "numeric"
  });
}
updateTime();
setInterval(updateTime, 60000);

/* ===== WIKIPEDIA ===== */
function isCalm(t) {
  return !["war","killed","attack","bomb","battle"].some(w => t.toLowerCase().includes(w));
}

async function loadWikipediaEvent() {
  const d = new Date();
  const key = "wiki-" + d.toDateString();
  const cached = localStorage.getItem(key);
  if (cached) { historyEl.textContent = cached; return; }

  const m = String(d.getMonth()+1).padStart(2,"0");
  const day = String(d.getDate()).padStart(2,"0");

  try {
    const r = await fetch(`https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/${m}/${day}`);
    const j = await r.json();
    const events = j.events || [];
    const e = events.find(x => x?.text && isCalm(x.text)) || events[0];
    const text = e ? `in ${e.year}, ${e.text}` : "nothing recorded.";
    localStorage.setItem(key, text);
    historyEl.textContent = text;
  } catch {
    historyEl.textContent = "no data today.";
  }
}
loadWikipediaEvent();

/* ===== STOCKS (calls Python backend) ===== */
function fmtPct(v) {
  if (v == null) return "—";
  return `<span class="${v >= 0 ? "pos" : "neg"}">${v.toFixed(2)}%</span>`;
}

async function fetchStock(sym) {
  const r = await fetch(`/api/stock?symbol=${encodeURIComponent(sym)}`);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "stock error");
  return j;
}

async function loadStocks() {
  stockRowsEl.innerHTML = "";
  const syms = tickersEl.value
    .split(",")
    .map(s => s.trim().toUpperCase())
    .filter(Boolean)
    .slice(0, 10);

  for (const sym of syms) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${sym}</td><td colspan="4">loading…</td>`;
    stockRowsEl.appendChild(tr);

    try {
      const s = await fetchStock(sym);
      tr.innerHTML = `
        <td>${sym}</td>
        <td>$${s.price ?? "—"}</td>
        <td>${fmtPct(s.day)}</td>
        <td>${fmtPct(s.mo)}</td>
        <td>${fmtPct(s.yr)}</td>`;
    } catch (e) {
      console.error("stock error", sym, e);
      tr.innerHTML = `<td>${sym}</td><td colspan="4">error</td>`;
    }
  }
}

loadBtn.addEventListener("click", loadStocks);

</script>
</body>
</html>
"""
    return Response(html, mimetype="text/html")

if __name__ == "__main__":
    # Visit http://127.0.0.1:5000
    app.run(host="127.0.0.1", port=5000, debug=True)




