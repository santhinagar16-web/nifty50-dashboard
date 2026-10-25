"""
NSE Options Analytics + OI Event Detector — single-file Streamlit app.

UI: status pill + KPI row, then 4 tabs:
    🌊 OI & IV     — structure metrics, OI distribution, daily Δ, IV smile/skew, drilldown
    ✍️ Shorts Flow — writer-side ONLY (new shorts + short covering): KPIs,
                     a full-width filter strip, then a 2×2 grid —
                     interval ΔOI chart (bars tagged ✍️📈🚀📉 for writing /
                     buying / covering / long exit) beside the live shorts
                     table, IV shift beside the per-strike short book
    🚨 All Events — the full tinted events table with filters
    🗄 History     — PCR/spot/ATM-IV, IV history, DB stats

Data hygiene (this version):
  • Content-fingerprint stale detection — a fetched chain identical to the
    last fetch is skipped instantly; identical to the last STORED snapshot
    (restart / symbol round-trip) is never re-stored → no duplicate rows.
  • OI-lag updates captured — NSE refreshes OI fields irregularly,
    sometimes with unchanged volume; the old volume-only gate missed those.
  • NSE data-age tracking — the pill shows how old the exchange data
    actually is, and flags it stale during market hours.
  • Optional off-hours polling (sidebar toggle, gentle 60s cadence).
  • Self-healing NSE session — pnsea fetches its cookies ONCE and never
    refreshes them (they die after ~1-3 h → every poll fails), never
    times out a stalled request, and retries back-to-back with zero
    delay. This version adds a hard HTTP timeout, paced retries, and
    proactive/reactive session rebuilds — fixing the classic "works
    ~2 h, then poll errors + high CPU" death spiral.
  • UI renders on data changes only — a silent watcher checks the
    engine's data version every 10 s and re-renders the app only when a
    new/changed snapshot arrives (no more constant flicker and idle CPU
    burn).
  • Sidebar-adjustable ATM band, default ±300 points around spot.
  • Strike axes label EVERY bar — one x-tick per real strike at the
    bar's exact position (labels rotate, then step, as the band widens);
    bars never sit between two printed numbers again.
  • Readable events table — compact signed Δ OI (L/Cr), fixed column
    widths via column_config, tinted rows kept.

Fixes in this revision (full audit pass — 18 findings):
  • CRITICAL: the session-boundary guard ran BEFORE the stored-snapshot
    duplicate check, so an identical chain stored on a previous day was
    re-stored after every restart (phantom morning snapshot → wrong
    day-open, phantom events at open, 'Session Start' diffs vs
    yesterday's close). The duplicate verdict is now computed first;
    the day-guard only resets the diff baseline.
  • CRITICAL: events & snap_agg now have the same unique-index +
    INSERT OR IGNORE protection as option_chain — two app instances
    sharing one DB can no longer double-insert them. The one-time
    duplicate heal is flag-gated (app_meta) instead of full-scanning
    every boot.
  • Per-symbol engine pool (LRU-capped) — two tabs with different
    symbols no longer thrash a single shared engine.
  • Retry-button crash fixed (_fetch_expiries.clear → cached variant);
    chg_oi now selected on bootstrap (no false-zero 'Daily Δ OI'
    chart after restart); market-closed no longer misreported as STALE;
    symbol/expiry HTML-escaped; zero IVs masked in smile/skew/shift
    charts; OI-lag events score 0.65 instead of 0.4; 'Biggest |Δ OI|'
    sort + type filter are server-side; events-table cache busts on
    new data; OI/LTP schema drift fails loudly; PCR stored as NULL
    (not a fake 0.0) when undefined.
  • v2 (off-hours cache flip-flop — the 02:30/02:31 mirror-image event
    storms): after close, NSE's CDN alternates between cached copies of
    the final chain, so consecutive fetches ALWAYS differ from the
    previous one and the single-snapshot duplicate check let the whole
    flip-flop through — the closed chain was re-stored and re-diffed
    every poll, firing phantom "Long unwinding"/"New longs" events all
    night. Four layers now: event detection pauses while the market is
    closed (DETECT_OFFHOURS_EVENTS), a chain matching ANY of the last
    RECENT_FP_WINDOW stored fingerprints is a re-serve (skipped, never
    re-stored), a whole-chain OI flip with frozen premiums AND volumes
    is suppressed as a data revision, and a one-time heal purges the
    phantom off-hours events and duplicate pre-open chain rows already
    in the DB.

  • v2.1 (UX restructure): the Events tab was split — a dedicated
    "Shorts Flow" tab now shows ONLY writer-side activity (new shorts +
    short covering) with KPIs and a compact table (no type filter
    needed); the full mixed events table moved to its own "All Events"
    tab.
  • v2.2: the interval ΔOI / IV-shift lookback charts moved INTO the
    Shorts Flow tab (replacing its net-by-strike bar); the History tab
    keeps aggregates + DB stats only. The sidebar lookback selector
    still controls them.
  • v2.3 (interval-chart lag + short-book coverage): the lookback
    selector's new default "Last poll (live)" baselines both charts on
    the PREVIOUS stored snapshot — the exact pair the detector just
    diffed — and the snapshot loaders now cache-bust on data_version,
    so the charts refresh in the SAME rerun as the events table (the
    old ttl-only caching let them trail by up to 30 s after every new
    poll). New per-strike tracked SHORT BOOK: every ✍️ write adds to a
    strike's book, every 🚀 cover burns it down — cover rows read
    "covered X of Y tracked (Z%)" and a Short-book table shows
    written / covered / still-open per strike. The ledger spans the
    whole expiry, because shorts written on earlier days of this
    expiry are exactly the ones getting covered today.
  • v2.4 (new NSE close + side-by-side layout): NSE moved the F&O
    closing bell 15:30 → 15:40 effective 2026-08-03 — SESSION_END now
    matches, so events are detected through 15:40 instead of going
    silent for the last ten minutes of every session; the off-hours
    purge window and the sidebar session readout follow it, and the
    remaining 2026 NSE holidays are pre-filled in NSE_HOLIDAYS. The
    Shorts Flow tab was re-laid-out as a 2×2 grid: the interval ΔOI
    chart beside the live shorts table, the IV-shift chart beside the
    short book (both tables gained a compact mode for half width).
  • v2.5 (writer-graph removal + CSS-leak fix): the intraday cumulative
    writer-flow chart was removed from the Shorts Flow tab (user
    request — the interval ΔOI chart beside the table carries the same
    story per poll); the tab now opens with the KPI row straight into
    the 2×2 grid. Bug fix: the v2.4 compact-mode rewrite dropped the
    closing '>' from the events-table and short-book <div> opening
    tags, which swallowed each <style> block into the tag and leaked
    the raw CSS onto the page as text — both opening tags now close
    properly and the tables render styled again.
  • v2.6 (chart-vs-table alignment): the shorts table's header,
    filters and count caption moved out of the table's grid column
    into a full-width strip above the grid — inside the column they
    added ~300 px above the table, so the Interval ΔOI chart sat
    noticeably ABOVE the shorts table instead of beside it (user
    report). Chart and table now start at the same y, and the chart
    heights match the table caps (380 px) so each pair aligns at both
    edges. Widget keys unchanged, so filter state survives.
  • v2.7 (bar activity tags): every Interval ΔOI bar now carries a tag
    at its outer end — ✍️ writing, 📈 buying (new longs), 🚀 covering,
    📉 long exit — read from the same OI × premium quadrant the
    detector uses (including the ±0.5% flat band and its tie-breaks),
    so a strike's bars say what the flow is without cross-referencing
    the table. Tags draw only for bars ≥ 500 Δ OI (REL_MIN_ABS — the
    smallest move the detector itself would mint); sub-threshold
    noise stays clean. Positive bars tag above, negative below the
    tip, and hovering a tag shows the activity word plus the OI move.
  • v2.8 (per-bar strike labels): every strike-axis chart — OI
    distribution, daily Δ OI, interval ΔOI, IV smile/skew and IV shift —
    now pins one x-axis label at EVERY bar's exact strike (array-mode
    ticks) instead of plotly's default "nice" values (24,500 / 25,000),
    which the bars sat BETWEEN — the x-axis never said which strike a
    bar was (user report). Labels stay flat while they fit, rotate 45°
    then 90° as the sidebar ATM band widens, and step to every other
    strike only past 48 strikes (hover always names the exact strike).
    The spot line, colors and the v2.7 activity tags are unchanged.

Engine: atomic snapshot writes, side-aware event bias, hourly pruning,
7-day retention, unique-index protection against duplicate rows.

Requirements:
    pip install "streamlit>=1.46" "plotly>=5" "pandas>=1.5" pnsea
Run:
    streamlit run app.py
"""

import asyncio
import gc
import hashlib
import html
import logging
import math
import random
import sqlite3
import sys
import threading
import time
import warnings
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

try:
    from pnsea import NSE
    PNSEA_AVAILABLE = True
except ImportError:
    PNSEA_AVAILABLE = False

# Windows asyncio fix — pnsea uses aiohttp, which wants a selector loop.
# Python 3.14+ deprecates the policy API (removal in 3.16), so:
#   • use the policy while it exists, with its deprecation warning silenced
#   • the poller thread ALSO installs a selector loop directly via
#     asyncio.set_event_loop() (not deprecated) — see _poll_loop()
if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass


# ═══════════════════════════════ CONFIG ═══════════════════════════════
IST               = ZoneInfo("Asia/Kolkata")
# Anchor the SQLite file to THIS script's folder, not the launch folder —
# the old relative path silently created a brand-new empty DB whenever the
# app was started from a different working directory (e.g. a .bat in
# another folder), making all previously stored history "disappear".
DB_PATH           = str(Path(__file__).resolve().parent / "options_history.db")
POLL_SECONDS      = 15          # background poller cadence (market hours)
OFFHOURS_POLL_SECONDS = 60      # gentle cadence outside market hours
BOOTSTRAP_RETRY_SECONDS = 30   # re-seed attempts while the DB looks empty
                               # (the file is often copied in AFTER launch)
REFRESH_SECONDS   = 10          # UI data-change check cadence (renders only on new data)
SESSION_START     = (9, 15)     # IST
SESSION_START     = (9, 15)     # IST
# v2.4: NSE extended the equity-derivatives (F&O) closing bell from
# 15:30 to 15:40 effective 2026-08-03 (NSE circular + the exchange's
# market-timings page: "Normal Market Close Time 15:40 hrs" for the
# derivatives session). This app tracks F&O chains, so event
# detection now runs through 15:40 — with the old 15:30 bound the last
# ten minutes of every session went silent.
SESSION_END       = (15, 40)    # IST
MARKET_HOURS_ONLY = True        # engine default; sidebar toggle overrides
NSE_STALE_SECONDS = 180         # flag "NSE data stale" after this long
                                # without a content change (market hours)
RETENTION_DAYS    = 7           # raw snapshot retention

# ── off-hours cache flip-flop guards (v2) ────────────────────────────
# After close, NSE's CDN alternates between cached copies of the final
# chain (nodes hold slightly different post-close OI reconciliations).
# Consecutive fetches then ALWAYS differ from the previous one, so a
# single-snapshot duplicate check lets the whole flip-flop through.
DETECT_OFFHOURS_EVENTS = False  # market closed → store snapshots, but never
                                # diff them (no trading = no real events)
RECENT_FP_WINDOW       = 8      # fingerprints remembered per symbol|expiry

# ── self-healing NSE session (fixes the ~2 h death spiral) ──────────
NSE_HTTP_TIMEOUT     = 15      # hard per-request timeout (curl_cffi)
NSE_HTTP_RETRY_DELAY = 1.5     # pause between HTTP-layer retry attempts
NSE_CLIENT_MAX_AGE   = 45 * 60 # rebuild session BEFORE its cookies die (~1-3 h)
NSE_REBUILD_ON_FAIL  = 3       # consecutive poll failures → rebuild session
NSE_REBUILD_MIN_GAP  = 120     # never rebuild more often than this (seconds)

# Palette — chosen for contrast on BOTH Streamlit themes. The old neon
# values (#00E676 green, #FFD700 gold) were designed for dark dashboards
# and were near-invisible on the default light theme.
CALL_COLOR = "#0B8A3E"          # calls / bullish (charts + accents)
PUT_COLOR  = "#D93025"          # puts  / bearish (charts + accents)
SPOT_COLOR = "#B45309"          # spot (amber-700: readable on white AND black)
TEXT_MAIN  = "#1F2937"          # near-black body text on light surfaces
TEXT_SUB   = "#4B5563"          # secondary gray text
TEXT_UP    = "#0B6E4F"          # bullish TEXT (dark green, WCAG-safe)
TEXT_DOWN  = "#B3261E"          # bearish TEXT (dark red,  WCAG-safe)
PCR_COLOR  = "#42A5F5"          # PCR lines
GRID_COLOR = "rgba(128,134,139,0.28)"   # neutral grid — visible on light AND dark

LOOKBACKS = {
    "Last poll (live)": 0,   # baseline = previous stored snapshot — the
                             # exact interval the detector just diffed, so
                             # the interval charts and the newest event
                             # rows are the same numbers in the same rerun
    "5 Minutes Ago":  5,
    "15 Minutes Ago": 15,
    "30 Minutes Ago": 30,
    "Session Start":  None,
}

PCR_BULLISH = 1.2
PCR_BEARISH = 0.7

# Event detector thresholds (what gets RECORDED; the Events-tab slider
# only filters the view — detection stays fixed so history is complete)
ABS_FLOOR   = 1500
REL_FLOOR   = 0.04
REL_MIN_ABS = 500     # the %-of-OI branch must ALSO clear |Δ OI| ≥ this —
                      # without it 100→104 contracts (4%) was an "event",
                      # while a strike jumping 0→1,499 was silently ignored
FRESH_PREV  = 500
FRESH_NEW   = 3000
MASS_UNWIND = -0.25
MASS_UNWIND_MIN_OI = 5000   # "mass unwind" needs a real position first —
                            # 2,000→0 contracts is not a mass unwind

CLASS_META = {
    "NEW_LONGS":     {"sign": "bull", "label": "New longs"},
    "NEW_SHORTS":    {"sign": "bear", "label": "New shorts"},
    "SHORT_COVER":   {"sign": "bull", "label": "Short covering"},
    "LONG_UNWIND":   {"sign": "bear", "label": "Long unwinding"},
    "FRESH_BUILDUP": {"sign": "info", "label": "Fresh buildup"},
    "MASS_UNWIND":   {"sign": "warn", "label": "Mass unwind"},
}
SIGN_EMOJI = {"bull": "🟢", "bear": "🔴", "info": "🔵", "warn": "🟠"}

# v2.7 — per-bar activity tags for the Interval ΔOI chart (user request).
# The same 2×2 quadrant the detector reads — OI change × premium change
# — compressed into one emoji above each bar. Emojis match the events
# table's Signal column, so the chart and the table read as one view.
ACTIVITY_META = {
    "NEW_SHORTS":  ("✍️", "writing",    "#B3261E"),
    "NEW_LONGS":   ("📈", "buying",     "#0B6E4F"),
    "SHORT_COVER": ("🚀", "covering",   "#0B57D0"),
    "LONG_UNWIND": ("📉", "long exit",  "#9A6A00"),
}
ACTIVITY_TAG_FLOOR = 500   # = REL_MIN_ABS: the smallest move the
                           # detector itself would ever mint; bars below
                           # this are sub-threshold noise and stay untagged

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("nse_app")

# ═══════════════════════ NSE HTTP-STACK HARDENING ═══════════════════════
# pnsea → stealthkit → curl_cffi has three defects that kill any
# long-running poller (your symptoms: ~2 h in → poll errors, no data,
# high CPU):
#   1. NSE cookies are fetched ONCE at startup and NEVER refreshed.
#      They typically expire after ~1-3 h, after which every API call
#      returns 401/403 or an HTML block page — the poller then fails
#      forever ("FETCH ISSUES / not fetching data").
#   2. No request timeout anywhere — one stalled NSE connection hangs
#      the poller thread forever while it holds the NSE lock.
#   3. stealthkit's internal retry loop fires attempts back-to-back
#      (its sleep is commented out) and swallows errors into None, so a
#      dead session becomes a request storm with fresh TLS handshakes
#      every few seconds → sustained high CPU.


def _build_nse_client():
    """Fresh NSE client = fresh cookies. Used at startup and for every
    scheduled/reactive rebuild — the only reliable way to refresh NSE's
    short-lived cookies, which pnsea never does on its own."""
    client = NSE()
    client.session.retries = 2      # paced by the patched request() below
    return client


def _harden_nse_http_stack():
    """Timeout + paced-retry patches, applied once at import."""
    # 1) hard timeout on EVERY curl_cffi request (incl. cookie bootstrap)
    try:
        import curl_cffi.requests as _cffi
        _orig_cffi_request = _cffi.Session.request

        def _cffi_request_with_timeout(self, method, url, **kwargs):
            kwargs.setdefault("timeout", NSE_HTTP_TIMEOUT)
            return _orig_cffi_request(self, method, url, **kwargs)

        _cffi.Session.request = _cffi_request_with_timeout
    except Exception as exc:                      # pragma: no cover
        logger.warning("curl_cffi timeout patch skipped: %s", exc)

    # 2) replace stealthkit's zero-delay retry loop with paced retries
    #    that RAISE on exhaustion (it used to return None after instant
    #    retries, which then blew up inside pnsea as AttributeError)
    try:
        from stealthkit.stealth import StealthSession

        def _paced_request(self, method, url, **kwargs):
            kwargs.setdefault("timeout", NSE_HTTP_TIMEOUT)
            attempts = max(1, int(getattr(self, "retries", 1) or 1))
            last_exc: Optional[BaseException] = None
            for attempt in range(attempts):
                try:
                    resp = self.session.request(method, url, **kwargs)
                    if resp is not None:
                        return resp
                    last_exc = ConnectionError(f"empty response from {url}")
                except Exception as exc:
                    last_exc = exc
                if attempt < attempts - 1:
                    time.sleep(NSE_HTTP_RETRY_DELAY * (attempt + 1))
            raise last_exc if last_exc else ConnectionError(f"request failed: {url}")

        StealthSession.request = _paced_request
    except Exception as exc:                      # pragma: no cover
        logger.warning("StealthSession retry patch skipped: %s", exc)


_harden_nse_http_stack()

EXPIRY_FORMATS = ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y")

# ----------------------------------------------------------------------
# Symbol universe — indices first, then F&O stocks (alphabetical).
# ----------------------------------------------------------------------
SYMBOLS = [
    # ---- indices ----
    "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50",
    # ---- F&O stocks ----
    "AARTIIND", "ABB", "ABBOTINDIA", "ACC", "ADANIENSOL", "ADANIENT",
    "ADANIGREEN", "ADANIPORTS", "ALKEM", "AMBUJACEM", "ANGELONE",
    "APLAPOLLO", "APOLLOHOSP", "APOLLOTYRE", "ASHOKLEY", "ASIANPAINT",
    "ASTRAL", "ATUL", "AUBANK", "AUROPHARMA", "AXISBANK", "BAJAJ-AUTO",
    "BAJAJFINSV", "BAJFINANCE", "BALKRISIND", "BANDHANBNK", "BANKBARODA",
    "BANKINDIA", "BATAINDIA", "BEL", "BERGEPAINT", "BHARATFORG",
    "BHARTIARTL", "BHEL", "BIOCON", "BOSCHLTD", "BPCL", "BRITANNIA",
    "BSOFT", "BSE", "CAMS", "CANBK", "CANFINHOME", "CHAMBLFERT",
    "CHOLAFIN", "CIPLA", "COALINDIA", "COFORGE", "COLPAL", "CONCOR",
    "COROMANDEL", "CROMPTON", "CUMMINSIND", "CYIENT", "DABUR",
    "DALBHARAT", "DEEPAKNTR", "DELHIVERY", "DIVISLAB", "DIXON", "DLF",
    "DMART", "DRREDDY", "EICHERMOT", "ESCORTS", "EXIDEIND", "FEDERALBNK",
    "GAIL", "GLENMARK", "GMRAIRPORT", "GNFC", "GODREJCP", "GODREJPROP",
    "GRANULES", "GRASIM", "GUJGASLTD", "HAL", "HAVELLS", "HCLTECH",
    "HDFCAMC", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HFCL", "HINDALCO",
    "HINDCOPPER", "HINDPETRO", "HINDUNILVR", "ICICIBANK", "ICICIGI",
    "ICICIPRULI", "IDEA", "IDFCFIRSTB", "IEX", "IGL", "INDHOTEL",
    "INDIACEM", "INDIAMART", "INDIGO", "INDUSINDBK", "INDUSTOWER", "INFY",
    "IOC", "IPCALAB", "IRCTC", "ITC", "JINDALSTEL", "JIOFIN", "JKCEMENT",
    "JSWENERGY", "JSWSTEEL", "JUBLFOOD", "KALYANKJIL", "KEI", "KOTAKBANK",
    "KPITTECH", "LAURUSLABS", "LICHSGFIN", "LT", "LTF", "LTIM", "LTTS",
    "LUPIN", "M&M", "M&MFIN", "MANAPPURAM", "MARICO", "MARUTI",
    "MAXHEALTH", "MCX", "METROPOLIS", "MFSL", "MGL", "MOTHERSON",
    "MPHASIS", "MRF", "MUTHOOTFIN", "NATIONALUM", "NAUKRI", "NAVINFLUOR",
    "NCC", "NESTLEIND", "NHPC", "NMDC", "NTPC", "NYKAA", "OBEROIRLTY",
    "OFSS", "ONGC", "PAGEIND", "PEL", "PERSISTENT", "PETRONET", "PFC",
    "PIDILITIND", "PIIND", "PNB", "POLICYBZR", "POLYCAB", "POONAWALLA",
    "POWERGRID", "PRESTIGE", "PVRINOX", "RAMCOCEM", "RBLBANK", "RECLTD",
    "RELIANCE", "SAIL", "SBICARD", "SBILIFE", "SBIN", "SHREECEM",
    "SHRIRAMFIN", "SIEMENS", "SRF", "SUNPHARMA", "SUNTV", "SYNGENE",
    "TATACHEM", "TATACOMM", "TATACONSUM", "TATAMOTORS", "TATAPOWER",
    "TATASTEEL", "TCS", "TECHM", "TITAGARH", "TITAN", "TORNTPHARM",
    "TORNTPOWER", "TRENT", "TVSMOTOR", "UBL", "ULTRACEMCO", "UNIONBANK",
    "UPL", "VEDL", "VOLTAS", "WIPRO", "YESBANK", "ZEEL", "ZOMATO",
    "ZYDUSLIFE",
]

# ATM window in POINTS around spot — sidebar-adjustable, default ±300.
ATM_BAND_DEFAULT = 300
ATM_BAND_MIN     = 50
ATM_BAND_MAX     = 2000


# ═══════════════════════════════ SMALL HELPERS ═══════════════════════════════
# NSE trading holidays (IST) — "YYYY-MM-DD" strings from the official
# NSE holiday list (nseindia.com → Learn → Holidays). Without them, the
# poller burns retries and session rebuilds on exchange holidays that
# fall on weekdays. Refresh the list each January (past dates are
# harmless). Remaining 2026, per the official list: Gandhi Jayanti,
# Dussehra, Diwali-Balipratipada, Guru Nanak Jayanti, Christmas.
NSE_HOLIDAYS = {"2026-10-02", "2026-10-20", "2026-11-10",
                "2026-11-24", "2026-12-25"}


def market_open(now: Optional[datetime] = None) -> bool:
    """NSE F&O session, Mon–Fri 09:15–15:40 IST (holidays via
    NSE_HOLIDAYS — close extended 15:30 → 15:40 on 2026-08-03)."""
    now = now or datetime.now(IST)
    if now.weekday() >= 5:
        return False
    if now.date().isoformat() in NSE_HOLIDAYS:
        return False
    mins = now.hour * 60 + now.minute
    return (SESSION_START[0] * 60 + SESSION_START[1]) <= mins < \
           (SESSION_END[0] * 60 + SESSION_END[1])


def fmt_cnt(x) -> str:
    """Compact Indian number formatting (Lakh / Crore)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    x = float(x)
    if abs(x) >= 1e7:
        return f"{x / 1e7:.2f} Cr"
    if abs(x) >= 1e5:
        return f"{x / 1e5:.2f} L"
    return f"{x:,.0f}"


def signed_cnt(x) -> str:
    """Compact SIGNED Indian formatting for Δ columns (+1.25 L / -2.10 Cr)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    x = float(x)
    sign = "+" if x > 0 else ("-" if x < 0 else "")
    a = abs(x)
    if a >= 1e7:
        return f"{sign}{a / 1e7:,.2f} Cr"
    if a >= 1e5:
        return f"{sign}{a / 1e5:,.2f} L"
    if a >= 1e3:
        return f"{sign}{a / 1e3:,.1f} K"
    return f"{sign}{a:,.0f}"


def event_sign(cls: str, side: str) -> str:
    """Bull/bear reading depends on the instrument side.
    e.g. 'NEW_SHORTS' on a PE (put writers) is bullish, not bearish.
    Hardened with .get() — an unknown classification in the DB can't crash."""
    s = CLASS_META.get(cls, {}).get("sign", "info")
    if side == "PE" and s in ("bull", "bear"):
        return "bear" if s == "bull" else "bull"
    return s


def _chain_fingerprint(df: pd.DataFrame) -> str:
    """Content fingerprint of a chain snapshot (strike/type/OI/volume/LTP).

    Used for stale-data / duplicate detection:
      • identical to the last fetch      → skip instantly (NSE cache)
      • identical to the last STORED row → don't re-store (restart, symbol
        round-trip) — no duplicate history rows
    IV is deliberately excluded (derived from LTP; rounding noise would
    cause false 'new' verdicts). OI IS included even though NSE refreshes
    it on a lag with unchanged volume — those updates must be captured.
    """
    rows = sorted(
        (round(float(r.strike), 2), str(r.type),
         round(float(r.oi)), round(float(r.volume)), round(float(r.ltp), 2))
        for r in df.itertuples(index=False)
    )
    return hashlib.sha1(repr(rows).encode()).hexdigest()


def _looks_like_data_revision(merged: pd.DataFrame) -> bool:
    """FIX #21 — signature of a cached-copy swap / exchange data revision:
    MOST of the chain's OI changes in one step while premium and volume
    stay frozen on every moving row. Real OI changes require traded
    volume (every contract opened/closed IS a trade) and move premiums;
    revisions don't. Caught live as the 02:30/02:31 mirror-image event
    storm — every row 'flat price', Prem +0.0%."""
    if len(merged) < 4:
        return False
    d_oi  = merged["oi_new"].fillna(0.0) - merged["oi_prev"].fillna(0.0)
    d_ltp = merged["ltp_new"].fillna(0.0) - merged["ltp_prev"].fillna(0.0)
    d_vol = merged["volume_new"].fillna(0.0) - merged["volume_prev"].fillna(0.0)
    moving = d_oi != 0
    if int(moving.sum()) < max(4, len(merged) // 2):
        return False                      # not a whole-chain flip
    return bool((d_ltp[moving] == 0).all() and (d_vol[moving] == 0).all())


# ═══════════════════════════════ EVENT / ANALYSIS HELPERS ═══════════════════════════════
def classify_event(d_oi, d_pct, prev_oi, new_oi, side, spot, strike) -> Tuple[str, str]:
    m = "ITM" if (strike < spot if side == "CE" else strike > spot) else "OTM"
    if prev_oi < FRESH_PREV and new_oi > FRESH_NEW:
        # keep the neutral 'info' label, but show the premium move — a
        # strike coming alive with prem −50% is writers, +50% is buyers;
        # the old note hid that context completely
        return "FRESH_BUILDUP", (f"{m} strike came alive — OI "
                                 f"{prev_oi:.0f}→{new_oi:.0f}, prem {d_pct:+.1f}%")
    if (prev_oi >= MASS_UNWIND_MIN_OI
            and d_oi / prev_oi <= MASS_UNWIND):
        return "MASS_UNWIND", f"{m} — {abs(d_oi / prev_oi * 100):.0f}% of OI closed"
    if d_oi > 0:
        if d_pct > 0.5:
            return "NEW_LONGS", f"{m} — buyers dominant, prem +{d_pct:.1f}%"
        if d_pct < -0.5:
            return "NEW_SHORTS", f"{m} — writers dominant, prem {d_pct:.1f}%"
        return ("NEW_LONGS" if d_pct >= 0 else "NEW_SHORTS",
                f"{m} — flat price, net OI add {d_oi:+.0f}")
    if d_pct > 0.5:
        return "SHORT_COVER", f"{m} — buyback lifting prem +{d_pct:.1f}%"
    if d_pct < -0.5:
        return "LONG_UNWIND", f"{m} — longs exiting, prem {d_pct:.1f}%"
    return "LONG_UNWIND", f"{m} — OI removed, price flat"


def _interval_activity(df, flat_pct=0.5):
    """Chart-side twin of classify_event's 2×2: tags every interval bar
    writing / buying / covering / long exit from OI change × premium
    change, with the same ±0.5% flat band and tie-breaks the detector
    uses. Returns a COPY with an 'act' column — the caller's frame
    (merged, reused by the IV-shift chart) is never mutated. Returns
    the frame unchanged when no baseline LTP exists."""
    if not {"ltp", "ltp_past"}.issubset(df.columns):
        return df
    d = df.copy()
    prev = d["ltp_past"].where(d["ltp_past"] > 0)
    d["prem_pct"] = (d["ltp"] - d["ltp_past"]) / prev * 100

    def tag(r):
        doi = r["oi_delta"]
        dp = r["prem_pct"] if pd.notna(r["prem_pct"]) else 0.0
        if doi == 0:
            return None
        if doi > 0:
            if dp > flat_pct:
                return "NEW_LONGS"       # OI up, prem up — buying
            if dp < -flat_pct:
                return "NEW_SHORTS"      # OI up, prem down — writing
            return "NEW_LONGS" if dp >= 0 else "NEW_SHORTS"  # flat tie
        if dp > flat_pct:
            return "SHORT_COVER"        # OI down, prem up — covering
        if dp < -flat_pct:
            return "LONG_UNWIND"        # OI down, prem down — exit
        return "LONG_UNWIND"            # flat tie — matches the detector

    d["act"] = d.apply(tag, axis=1)
    return d


def _fmt_pcr(x) -> str:
    """PCR display helper — an undefined ratio (None) shows as '–', not 0.00."""
    return f"{x:.2f}" if x else "–"


def summarize_events(events, prev_spot, spot, prev_pcr, pcr) -> str:
    if not events:
        return "No significant OI changes in this interval."
    mv = (spot - prev_spot) / prev_spot * 100 if prev_spot else 0
    out = [f"Spot {'+' if mv >= 0 else ''}{mv:.2f}% · "
           f"PCR {_fmt_pcr(prev_pcr)}→{_fmt_pcr(pcr)}"]
    for cls in CLASS_META:
        evs = [e for e in events if e["classification"] == cls]
        if evs:
            t = max(evs, key=lambda e: abs(e["prem_impact"]))
            p = t["prem_impact"]
            emoji = SIGN_EMOJI.get(event_sign(cls, t["side"]), "")
            out.append(
                f"{emoji} **{CLASS_META[cls]['label']}**: {len(evs)} strike(s) · "
                f"largest {t['strike']:,.0f} {t['side']} ({t['d_oi']:+,.0f} OI, "
                f"₹{abs(p) / 1e5:.1f}L {'added' if p > 0 else 'removed'}) — {t['note']}")
    return "\n".join(out)


def max_pain(df: pd.DataFrame) -> Optional[float]:
    """Strike where option writers suffer the least pain at expiry."""
    ce = df[df["type"] == "CE"].groupby("strike")["oi"].sum()
    pe = df[df["type"] == "PE"].groupby("strike")["oi"].sum()
    strikes = sorted(set(ce.index) | set(pe.index))
    if not strikes:
        return None
    best_k, best_p = None, None
    for t in strikes:
        pain = (sum(oi * (t - k) for k, oi in ce.items() if t > k) +
                sum(oi * (k - t) for k, oi in pe.items() if k > t))
        if best_p is None or pain < best_p:
            best_k, best_p = t, pain
    return best_k


def atm_iv_of(df: pd.DataFrame, spot: float) -> Optional[float]:
    """Average CE + PE IV at the nearest strike."""
    if df is None or df.empty:
        return None
    atm_k = df.loc[(df["strike"] - spot).abs().idxmin(), "strike"]
    v = pd.to_numeric(df.loc[df["strike"] == atm_k, "iv"], errors="coerce")
    v = v[v > 0]
    return float(v.mean()) if len(v) else None


def compute_pcr(df):
    call_oi  = df.loc[df["type"] == "CE", "oi"].sum()
    put_oi   = df.loc[df["type"] == "PE", "oi"].sum()
    call_vol = df.loc[df["type"] == "CE", "volume"].sum()
    put_vol  = df.loc[df["type"] == "PE", "volume"].sum()
    pcr_oi  = put_oi  / call_oi  if call_oi  > 0 else None
    pcr_vol = put_vol / call_vol if call_vol > 0 else None
    return pcr_oi, pcr_vol


def compute_atm_pcr(df, spot):
    strikes = df["strike"].unique()
    if len(strikes) == 0:
        return None
    atm = min(strikes, key=lambda s: abs(s - spot))
    call_oi = df.loc[(df["type"] == "CE") & (df["strike"] == atm), "oi"].sum()
    put_oi  = df.loc[(df["type"] == "PE") & (df["strike"] == atm), "oi"].sum()
    return put_oi / call_oi if call_oi > 0 else None


def pcr_sentiment(pcr):
    if pcr is None:
        return "No data", "gray"
    if pcr >= PCR_BULLISH:
        return "Bullish bias (put writing)", CALL_COLOR
    if pcr <= PCR_BEARISH:
        return "Bearish bias (call writing)", PUT_COLOR
    return "Neutral zone", "#FFFFFF"


def analyze_trend(ts_data):
    if len(ts_data) < 2:
        return "Accumulating Data...", "gray"
    first, last = ts_data.iloc[0], ts_data.iloc[-1]
    oi_diff  = last["oi"]  - first["oi"]
    ltp_diff = last["ltp"] - first["ltp"]
    if oi_diff > 0 and ltp_diff > 0:  return "Long Buildup 🐂 (Bullish)",   CALL_COLOR
    if oi_diff > 0 and ltp_diff <= 0: return "Short Buildup 🧱 (Bearish)",  PUT_COLOR
    if oi_diff < 0 and ltp_diff > 0:  return "Short Covering 🚀 (Bullish)", CALL_COLOR
    if oi_diff < 0 and ltp_diff <= 0: return "Long Unwinding 📉 (Bearish)", PUT_COLOR
    return "Neutral ⚖️", "gray"


# ═══════════════════════════════ DATABASE ═══════════════════════════════
_CREATE_OPTION_CHAIN = """
CREATE TABLE IF NOT EXISTS option_chain (
    timestamp  TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    expiry     TEXT NOT NULL,
    strike     REAL NOT NULL,
    type       TEXT NOT NULL,
    iv         REAL, oi REAL, chg_oi REAL, volume REAL, ltp REAL,
    spot_price REAL
)"""

_CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, symbol TEXT, expiry TEXT, strike REAL, side TEXT,
    d_oi REAL, d_vol REAL, d_ltp_pct REAL,
    prev_oi REAL, new_oi REAL, prev_ltp REAL, new_ltp REAL,
    prem_impact REAL, classification TEXT, confidence REAL, note TEXT
)"""

_CREATE_SNAP_AGG = """
CREATE TABLE IF NOT EXISTS snap_agg (
    ts TEXT, symbol TEXT, expiry TEXT,
    spot REAL, atm_iv REAL, tot_ce_oi REAL, tot_pe_oi REAL, pcr REAL
)"""

_CREATE_APP_META = """
CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY, value TEXT
)"""

HIST_COLS  = ("timestamp", "symbol", "expiry", "strike", "type", "iv", "oi",
              "chg_oi", "volume", "ltp", "spot_price")
EVENT_COLS = ("ts", "symbol", "expiry", "strike", "side", "d_oi", "d_vol",
              "d_ltp_pct", "prev_oi", "new_oi", "prev_ltp", "new_ltp",
              "prem_impact", "classification", "confidence", "note")
AGG_COLS   = ("ts", "symbol", "expiry", "spot", "atm_iv", "tot_ce_oi",
              "tot_pe_oi", "pcr")


@contextmanager
def _ui_db():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    try:
        yield conn
    finally:
        conn.close()


def _insert_many(conn, table, cols, rows, ignore=False):
    if not rows:
        return
    verb = "INSERT OR IGNORE INTO" if ignore else "INSERT INTO"
    conn.executemany(
        f"{verb} {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        rows)


def _empty_past() -> pd.DataFrame:
    return pd.DataFrame({
        "strike": pd.Series(dtype="float64"),
        "type":   pd.Series(dtype="object"),
        "iv":     pd.Series(dtype="float64"),
        "oi":     pd.Series(dtype="float64"),
        "volume": pd.Series(dtype="float64"),
        "ltp":    pd.Series(dtype="float64"),
    })


def _expiry_sort_key(s: str) -> str:
    """ISO-sortable key for the mixed expiry string formats NSE uses
    (plain 'YYYY-MM-DD' sorts differently than 'DD-Mon-YYYY' lexically)."""
    for fmt in EXPIRY_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except (TypeError, ValueError):
            continue
    return "9999-99-99"        # unparseable strings sink to the end


@st.cache_data(ttl=30)
def _db_expiries_cached(sym):
    """Expiries actually present in the local DB for this symbol.
    Offline fallback for when NSE won't serve an expiry list (after
    hours, weekend, hiccup) so stored history stays reachable."""
    try:
        with _ui_db() as conn:
            rows = conn.execute(
                "SELECT DISTINCT expiry FROM option_chain WHERE symbol=?",
                (sym,)).fetchall()
        return sorted({r[0] for r in rows if r[0]}, key=_expiry_sort_key)
    except Exception:
        return []


# ═══════════════════════════════ ENGINE ═══════════════════════════════
class NiftyOptionEngine:
    """Background poller + storage + event detector."""

    def __init__(self, symbol: str = "NIFTY",
                 db_path: str = DB_PATH, poll_seconds: int = POLL_SECONDS):
        self.symbol       = symbol
        self.db_path      = db_path
        self.poll_seconds = poll_seconds
        self.market_hours_only = MARKET_HOURS_ONLY   # sidebar toggle overrides

        self.nse           = _build_nse_client() if PNSEA_AVAILABLE else None
        self._nse_built_at = time.time()   # NSE session cookie-age clock
        self._last_rebuild = 0.0
        self._nse_rebuilds = 0
        self._heartbeat    = time.time()   # poller liveness (sidebar shows it)
        self._nse_lock    = threading.Lock()
        self.expiry: Optional[str] = None

        self._reset_state()

        self.is_running = False
        self.lock       = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._failures  = 0
        # first prune 1 h after launch — never at t=0. A just-restored DB
        # (old SQLite copied in) must get the chance to be SEEN by the
        # bootstrap seeder before retention scrubbing touches it.
        self._last_prune = time.time()

        # FIX #20: recent stored fingerprints per (symbol|expiry). Deduping
        # only against the LAST fetch / LAST stored snapshot let NSE's
        # off-hours cache flip-flop (state A → state B → A → B, one CDN
        # node per state) through every check — each fetch differed from
        # the immediately previous one, so each was "new" and the whole
        # alternation was re-stored and re-diffed forever.
        self._recent_fps: Dict[str, deque] = {}

        self._init_db()

    # -------------------- internals --------------------
    @contextmanager
    def _db(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._db() as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(option_chain)")]
            if cols and ("symbol" not in cols or "expiry" not in cols):
                conn.execute("DROP TABLE option_chain")
                logger.info("Rebuilt option_chain (symbol/expiry-aware schema)")
            conn.execute(_CREATE_OPTION_CHAIN)
            conn.execute(_CREATE_EVENTS)
            conn.execute(_CREATE_SNAP_AGG)
            conn.execute(_CREATE_APP_META)
            # One-time duplicate heal across ALL THREE tables, gated by a
            # flag in app_meta — the heal DELETEs used to run on EVERY
            # startup, full-scanning a multi-million-row table each boot.
            healed = conn.execute(
                "SELECT value FROM app_meta WHERE key='dedup_healed'"
            ).fetchone()
            if not healed:
                conn.execute("""DELETE FROM option_chain WHERE rowid NOT IN (
                                   SELECT MIN(rowid) FROM option_chain
                                   GROUP BY symbol, expiry, timestamp, strike, type)""")
                conn.execute("""DELETE FROM events WHERE rowid NOT IN (
                                   SELECT MIN(rowid) FROM events
                                   GROUP BY symbol, expiry, ts, strike, side)""")
                conn.execute("""DELETE FROM snap_agg WHERE rowid NOT IN (
                                   SELECT MIN(rowid) FROM snap_agg
                                   GROUP BY symbol, expiry, ts)""")
                conn.execute("INSERT OR REPLACE INTO app_meta (key, value) "
                             "VALUES ('dedup_healed', '1')")
                logger.info("One-time duplicate heal complete "
                            "(option_chain / events / snap_agg)")
            # FIX #22 (one-time, flag-gated): purge the damage the off-hours
            # cache flip-flop already did. No trading occurs outside
            # 09:15–15:40 IST Mon–Fri (the F&O close moved 15:30 → 15:40 on
            # 2026-08-03; the purge window follows SESSION_END), so every
            # event row stamped outside that window is a phantom
            # (mirror-image unwinding / re-long storms diffed between
            # NSE's cached copies). Malformed ts values yield NULL from
            # time() and are conservatively KEPT.
            ohe = conn.execute(
                "SELECT value FROM app_meta WHERE key='offhours_events_healed'"
            ).fetchone()
            if not ohe:
                cur = conn.execute(
                    "DELETE FROM events WHERE "
                    "CAST(strftime('%w', ts) AS INT) IN (0, 6) "
                    "OR time(ts) < '09:15:00' "
                    "OR time(ts) >= '15:40:00'")
                logger.info("One-time purge of off-hours phantom events: "
                            "%d rows removed", cur.rowcount)
                # …and collapse the duplicate pre-open chain copies the
                # flip-flop stored: per (symbol, expiry, date) keep only the
                # LAST snapshot before 09:15 — the state closest to the open
                conn.execute("""
                    DELETE FROM option_chain WHERE rowid IN (
                      SELECT oc.rowid FROM option_chain oc
                      WHERE time(oc.timestamp) < '09:15:00'
                        AND EXISTS (
                          SELECT 1 FROM option_chain oc2
                          WHERE oc2.symbol = oc.symbol
                            AND oc2.expiry = oc.expiry
                            AND substr(oc2.timestamp, 1, 10)
                                = substr(oc.timestamp, 1, 10)
                            AND time(oc2.timestamp) < '09:15:00'
                            AND oc2.timestamp > oc.timestamp))""")
                conn.execute("""
                    DELETE FROM snap_agg WHERE rowid IN (
                      SELECT s.rowid FROM snap_agg s
                      WHERE time(s.ts) < '09:15:00'
                        AND EXISTS (
                          SELECT 1 FROM snap_agg s2
                          WHERE s2.symbol = s.symbol
                            AND s2.expiry = s.expiry
                            AND substr(s2.ts, 1, 10) = substr(s.ts, 1, 10)
                            AND time(s2.ts) < '09:15:00'
                            AND s2.ts > s.ts))""")
                logger.info("Collapsed duplicate pre-open chain/agg copies "
                            "(kept the last snapshot before 09:15 per day)")
                conn.execute("INSERT OR REPLACE INTO app_meta (key, value) "
                             "VALUES ('offhours_events_healed', '1')")
            conn.execute("DROP INDEX IF EXISTS ix_oc")
            conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_oc
                            ON option_chain (symbol, expiry, timestamp, strike, type)""")
            # FIX: events / snap_agg get the same unique-index protection
            # as option_chain — combined with INSERT OR IGNORE at write
            # time, two app instances sharing one DB can no longer
            # double-insert events or aggregates
            conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_ev
                            ON events (symbol, expiry, ts, strike, side)""")
            conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_sa
                            ON snap_agg (symbol, expiry, ts)""")
            conn.execute("""CREATE INDEX IF NOT EXISTS ix_oc_ts
                            ON option_chain (symbol, expiry, timestamp)""")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_ev "
                         "ON events (symbol, expiry, ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_sa "
                         "ON snap_agg (symbol, expiry, ts)")
            # bare-time indexes: the hourly retention DELETE must not
            # full-scan a multi-million-row table (CPU spike every hour)
            conn.execute("CREATE INDEX IF NOT EXISTS ix_oc_time "
                         "ON option_chain (timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_ev_time "
                         "ON events (ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_sa_time "
                         "ON snap_agg (ts)")
            conn.commit()

    def _reset_state(self):
        self.flow_data       = pd.DataFrame()
        self.spot_price      = 0.0
        self.data_version    = 0     # bumped whenever new data reaches the UI
        self.last_updated    = None   # last successful FETCH (any content)
        self.last_change     = None   # last time content ACTUALLY changed
        self.last_fp         = None   # fingerprint of the last known content
        self.last_summary    = ""
        self.last_summary_ts = None
        self.prev_spot       = 0.0
        self.prev_pcr        = 0.0
        self._bootstrap_key  = None   # (symbol, expiry) of the last seed attempt
        self._bootstrap_ok   = False  # that attempt actually loaded history
        self._bootstrap_last_try = 0.0

    @staticmethod
    def _parse_expiry(expiry):
        if not isinstance(expiry, str):
            return None
        for fmt in EXPIRY_FORMATS:
            try:
                return datetime.strptime(expiry, fmt).date()
            except ValueError:
                continue
        return None

    def _prune_stale_data(self):
        try:
            today = datetime.now(IST).date()
            cutoff = (datetime.now(IST).replace(tzinfo=None)
                      - timedelta(days=RETENTION_DAYS)).isoformat(timespec="seconds")
            with self._db() as conn:
                rows = conn.execute(
                    "SELECT DISTINCT expiry FROM option_chain").fetchall()
                stale = [e for (e,) in rows
                         if (d := self._parse_expiry(e)) and d < today]
                for table, ts_col in (("option_chain", "timestamp"),
                                      ("events", "ts"),
                                      ("snap_agg", "ts")):
                    if stale:
                        conn.executemany(f"DELETE FROM {table} WHERE expiry=?",
                                         [(e,) for e in stale])
                    conn.execute(f"DELETE FROM {table} WHERE {ts_col} < ?", (cutoff,))
                if stale:
                    logger.info("Pruned expired expiries: %s", ", ".join(stale))
                conn.commit()
        except sqlite3.Error as exc:
            logger.warning("Prune failed: %s", exc)

    # -------------------- public API --------------------
    def get_expiries(self, retries: int = 3, delay: float = 2.0,
                     symbol: Optional[str] = None):
        # explicit symbol — the cached UI wrapper is keyed by the symbol it
        # ASKS for, not by engine state (two tabs switching symbols could
        # otherwise cache the wrong symbol's expiries under another's key)
        sym = symbol or self.symbol
        if not self.nse:
            return []
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                # bounded wait — fail FAST: paced poller retries can hold
                # the lock for ~50s, and the sidebar falls back to
                # DB-stored expiries for this round instead of hanging the
                # UI thread for the full window
                if not self._nse_lock.acquire(timeout=5):
                    logger.warning("NSE busy — expiry fetch skipped this round")
                    return []
                try:
                    data = self.nse.options.option_chain(sym)
                finally:
                    self._nse_lock.release()
                if data and len(data) >= 2:
                    return list(data[1])
                logger.warning("Unexpected expiry payload (%d/%d)", attempt, retries)
            except Exception as exc:
                last_exc = exc
                logger.warning("Expiry fetch failed (%d/%d): %s",
                               attempt, retries, exc)
            if attempt < retries:
                time.sleep(delay)
        if last_exc:
            logger.error("Giving up on expiry fetch: %s", last_exc)
            # rebuild ONLY on real fetch errors — the old unconditional
            # call also rebuilt on lock-contention skips, replacing a
            # perfectly healthy session for no reason
            self._rebuild_nse("repeated expiry-fetch failures")
        return []

    def set_symbol(self, symbol: str):
        with self.lock:
            if self.symbol == symbol:
                return
            self.symbol = symbol
            self.expiry = None
            self._reset_state()
        logger.info("Symbol switched to %s", symbol)

    def set_expiry(self, expiry: str):
        with self.lock:
            if self.expiry == expiry:
                return
            self.expiry = expiry
            self._reset_state()
        logger.info("Target expiry switched to %s", expiry)
        # (no prune here — the poller's hourly schedule already covers it;
        # firing whole-table DELETEs on every expiry click just burned CPU)

    def _rebuild_nse(self, reason: str):
        """Swap in a brand-new NSE client (fresh cookies). Fixes the #1
        long-run failure: pnsea fetches cookies once and never refreshes
        them, so after ~1-3 h every call fails until restart."""
        now = time.time()
        if now - self._last_rebuild < NSE_REBUILD_MIN_GAP:
            return
        self._last_rebuild = now             # set FIRST — serializes callers
        try:
            fresh = _build_nse_client()      # blocking bootstrap, no lock held
        except Exception as exc:
            logger.error("NSE session rebuild failed (%s): %s", reason, exc)
            return
        with self._nse_lock:
            old, self.nse = self.nse, fresh
            self._nse_built_at = now
            self._nse_rebuilds += 1
        if old is not None:
            try:
                old.session.session.close()  # release curl_cffi connections
            except Exception:
                pass
        del old
        gc.collect()
        logger.info("NSE session rebuilt (%s) — rebuild #%d",
                    reason, self._nse_rebuilds)

    def start_engine(self):
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._poll_loop,
                                        name="nse-poller", daemon=True)
        self._thread.start()

    def stop_engine(self):
        self.is_running = False

    def snapshot(self):
        # First render after startup/restart: seed the UI from the last
        # stored snapshot (if any) so the dashboard shows history right
        # away — especially outside market hours, when the next live
        # fetch may be hours away.
        self._bootstrap_from_db(self.symbol, self.expiry)
        with self.lock:
            return self.flow_data.copy(), self.spot_price, self.last_updated

    def status(self) -> Dict:
        with self.lock:
            return {"symbol": self.symbol, "expiry": self.expiry,
                    "last_updated": self.last_updated,
                    "last_change": self.last_change,
                    "failures": self._failures,
                    "data_version": self.data_version,
                    "session_age_min": int((time.time() - self._nse_built_at) // 60),
                    "rebuilds": self._nse_rebuilds,
                    "heartbeat_age": int(time.time() - self._heartbeat)}

    def summary(self) -> Tuple[str, Optional[str]]:
        with self.lock:
            return self.last_summary, self.last_summary_ts

    # -------------------- polling --------------------
    def _poll_loop(self):
        # pnsea's aiohttp-style calls want a selector loop in THIS thread
        # on Windows. asyncio.set_event_loop() is NOT deprecated (unlike
        # the policy API).
        if sys.platform == "win32":
            try:
                asyncio.set_event_loop(asyncio.SelectorEventLoop())
            except Exception:
                pass
        failures = 0
        while self.is_running:
            # top-level guard — the poller thread must NEVER die silently
            try:
                self._heartbeat = time.time()

                if time.time() - self._last_prune > 3600:
                    self._last_prune = time.time()
                    self._prune_stale_data()

                # proactive: NSE cookies live ~1-3 h — rebuild BEFORE they
                # die instead of waiting for a failure streak
                if time.time() - self._nse_built_at > NSE_CLIENT_MAX_AGE:
                    self._rebuild_nse("scheduled cookie refresh")

                with self.lock:
                    expiry, symbol = self.expiry, self.symbol
                if expiry and symbol:
                    # poll-loop side of the startup seed (covers the case
                    # where no UI rerun happened yet)
                    self._bootstrap_from_db(symbol, expiry)
                    m_open = market_open()
                    if self.market_hours_only and not m_open:
                        time.sleep(60)
                        continue
                    try:
                        self._refresh(symbol, expiry)
                        failures = 0
                        self._failures = 0
                    except Exception as exc:
                        failures += 1
                        self._failures = failures
                        wait = min(self.poll_seconds * failures, 60)
                        logger.warning("Chain fetch failed (%d in a row): %s — "
                                       "retry %ss", failures, exc, wait)
                        # reactive: a dead session (expired cookies) is the
                        # #1 cause of failure streaks — swap in a fresh one
                        if failures >= NSE_REBUILD_ON_FAIL:
                            self._rebuild_nse(f"{failures} consecutive fetch failures")
                        time.sleep(wait)
                        continue
                    # gentle cadence off-hours + small jitter (avoids
                    # metronome-regular requests); stale fetches are
                    # skipped by fingerprint anyway
                    cadence = self.poll_seconds if m_open else OFFHOURS_POLL_SECONDS
                    time.sleep(max(5, cadence + random.uniform(-1.5, 1.5)))
                    continue
                time.sleep(self.poll_seconds)
            except Exception as exc:
                logger.error("Poller recovered from unexpected error: %s", exc)
                time.sleep(5)

    def _refresh(self, symbol: str, expiry: str):
        with self._nse_lock:
            chain_data = self.nse.options.option_chain(symbol, expiry_date=expiry)
        if not chain_data or len(chain_data) < 3:
            raise ValueError("incomplete option-chain payload")

        df_raw = chain_data[0]
        spot = float(chain_data[2])
        if df_raw is None or df_raw.empty or spot <= 0:
            raise ValueError("empty chain or zero spot")

        found_cols = set()

        def col(prefix, suffix):
            for name in (f"{prefix}_{suffix}", f"{prefix}.{suffix}"):
                if name in df_raw.columns:
                    found_cols.add(f"{prefix}_{suffix}")
                    return pd.to_numeric(df_raw[name], errors="coerce")
            return pd.Series(0.0, index=df_raw.index)

        strikes = pd.to_numeric(df_raw["strikePrice"], errors="coerce")
        frames = []
        for opt_type in ("CE", "PE"):
            frames.append(pd.DataFrame({
                "strike": strikes,
                "iv":     col(opt_type, "impliedVolatility"),
                "oi":     col(opt_type, "openInterest"),
                "chg_oi": col(opt_type, "changeinOpenInterest"),
                "volume": col(opt_type, "totalTradedVolume"),
                "ltp":    col(opt_type, "lastPrice"),
                "type":   opt_type,
            }))
        combined = (pd.concat(frames, ignore_index=True)
                    .dropna(subset=["strike"])
                    # a duplicated NSE row would turn the prev/new merge into
                    # a Cartesian product → duplicated, wrong ΔOI events
                    .drop_duplicates(subset=["strike", "type"], keep="last")
                    .fillna(0.0))

        # fail loudly on payload schema drift — the zero-filled fallback
        # above used to turn a renamed OI/LTP column into a whole stored
        # chain of fake zeros (plus an event storm on the next snapshot)
        _need = {"CE_openInterest", "PE_openInterest",
                 "CE_lastPrice", "PE_lastPrice"}
        if not _need <= found_cols:
            raise ValueError("option-chain payload missing columns: "
                             f"{sorted(_need - found_cols)}")

        now = datetime.now(IST).replace(tzinfo=None)

        # ── stale / duplicate detection ────────────────────────────────
        # NSE serves its option chain on an irregular refresh cycle and
        # often returns a cached snapshot. Gate every store on a content
        # fingerprint instead of volume alone (OI can update with unchanged
        # volume — the volume-only gate used to miss those).
        fp = _chain_fingerprint(combined)

        with self.lock:
            if self.expiry != expiry or self.symbol != symbol:
                return
            if self.last_fp is not None and self.last_fp == fp:
                # identical to what we already hold — just refresh the
                # fetch timestamp so the UI knows the poller is alive
                self.last_updated = now
                return

        prev_ts, prev, db_spot, db_pcr = self._load_prev_chain(symbol, expiry)

        # ── duplicate-content verdict FIRST ────────────────────────────
        # FIX (critical): this check used to run AFTER the session-
        # boundary guard emptied `prev`, so it could only fire when the
        # last stored snapshot was from TODAY. After any restart or
        # symbol round-trip on a new day, an identical chain (NSE serves
        # yesterday's static final chain all night) sailed through and
        # was RE-STORED under today's timestamp — a phantom snapshot
        # that poisoned day-open, the 'Session Start' lookback and the
        # first diff of the day. The verdict must not depend on prev's
        # day.
        stored_dup = (not prev.empty) and _chain_fingerprint(prev) == fp

        # ── session-boundary guard: never diff OI across trading days ──
        # NSE resets change-in-OI and volume each session, so the first
        # poll of a new day must not diff today vs YESTERDAY's close
        # (phantom "events" at open, all stuck at confidence 0.4 because
        # the reset volume forced d_vol to 0). It now resets ONLY the
        # diff baseline — it no longer re-arms the store path.
        if prev_ts and not str(prev_ts).startswith(now.date().isoformat()):
            prev = prev.iloc[0:0]
            db_spot = db_pcr = 0.0

        if stored_dup:
            # identical to the last STORED snapshot (app restart, symbol
            # round-trip) — never re-store it as a duplicate
            self._remember_fp(symbol, expiry, fp)   # FIX #20: (re)seed ring
            with self.lock:
                if self.expiry != expiry or self.symbol != symbol:
                    return
                self.flow_data    = combined
                self.spot_price   = spot
                self.last_updated = now
                self.last_fp      = fp
                self.data_version += 1  # new to the UI after restart/round-trip
                if self.last_change is None and prev_ts:
                    try:
                        self.last_change = datetime.fromisoformat(prev_ts)
                    except ValueError:
                        pass
            logger.info("[%s %s] stale snapshot — identical to stored, skipped",
                        symbol, now.strftime("%H:%M:%S"))
            return

        if self._fp_is_recent(symbol, expiry, fp):
            # FIX #20: the chain matches a recently stored state but NOT
            # the last one — NSE's classic off-hours cache flip-flop
            # (A→B→A). Liveness bookkeeping only: no re-store, no diff,
            # no UI wake-up. This alternation is what produced the
            # mirror-image "Long unwinding"/"New longs" storms every
            # poll cycle while the market was closed.
            with self.lock:
                if self.expiry != expiry or self.symbol != symbol:
                    return
                self.last_updated = now
                self.last_fp      = fp
            logger.info("[%s %s] cache flip-flop — chain matches a recent "
                        "state, skipped", symbol, now.strftime("%H:%M:%S"))
            return

        # ── genuinely new content: events, aggregates, one atomic write ──
        # FIX #19: with the market closed there is no trading, so an OI
        # "change" between off-hours fetches is just NSE serving another
        # cached copy of the closed chain — store the snapshot (dedup'd
        # above), but never diff it into phantom events.
        m_open = market_open(now)
        if m_open or DETECT_OFFHOURS_EVENTS:
            events = self._detect_events(prev, combined, spot)
        else:
            events = []

        pcr_oi, _ = compute_pcr(combined)
        # store NULL when the ratio is undefined (no call OI) — the old
        # `or 0.0` wrote a fake 0.0 PCR into history, dipping the chart
        pcr_oi = float(pcr_oi) if pcr_oi is not None else None
        atm_iv = atm_iv_of(combined, spot)
        tot_ce = float(combined.loc[combined["type"] == "CE", "oi"].sum())
        tot_pe = float(combined.loc[combined["type"] == "PE", "oi"].sum())

        ts_s = now.isoformat(timespec="seconds")
        hist = [(ts_s, symbol, expiry, r.strike, r.type, r.iv, r.oi, r.chg_oi,
                 r.volume, r.ltp, spot)
                for r in combined.itertuples(index=False)]
        evs = [(ts_s, symbol, expiry, e["strike"], e["side"], e["d_oi"],
                e["d_vol"], e["d_ltp_pct"], e["prev_oi"], e["new_oi"],
                e["prev_ltp"], e["new_ltp"], e["prem_impact"],
                e["classification"], e["confidence"], e["note"])
               for e in events]
        agg = [(ts_s, symbol, expiry, spot, atm_iv, tot_ce, tot_pe, pcr_oi)]

        with self._db() as conn:
            # FIX: events / snap_agg now insert with OR IGNORE behind
            # their own unique indexes (see _init_db) — a second app
            # instance sharing this DB can no longer double-insert them
            _insert_many(conn, "option_chain", HIST_COLS, hist, ignore=True)
            _insert_many(conn, "events", EVENT_COLS, evs, ignore=True)
            _insert_many(conn, "snap_agg", AGG_COLS, agg, ignore=True)
            conn.commit()

        self._remember_fp(symbol, expiry, fp)   # FIX #20: it's stored now

        with self.lock:
            if self.expiry != expiry or self.symbol != symbol:
                return
            prev_spot = self.prev_spot or db_spot
            prev_pcr  = self.prev_pcr or db_pcr
            if prev_spot and events:
                self.last_summary = summarize_events(
                    events, prev_spot, spot, prev_pcr, pcr_oi)
                self.last_summary_ts = ts_s
            self.flow_data    = combined
            self.spot_price   = spot
            self.last_updated = now
            self.last_change  = now
            self.last_fp      = fp
            self.data_version += 1      # genuinely new snapshot → wake the UI
            self.prev_spot    = spot
            self.prev_pcr     = pcr_oi

        logger.info("[%s %s] snapshot | expiry %s | spot %.2f | events %d%s",
                    symbol, now.strftime("%H:%M:%S"), expiry, spot, len(events),
                    "" if (m_open or DETECT_OFFHOURS_EVENTS)
                    else " (market closed — detection paused)")

    # -------------------- persistence helpers --------------------
    def _bootstrap_from_db(self, symbol: Optional[str], expiry: Optional[str]):
        """Seed the UI from the last STORED snapshot so a freshly started app
        shows the most recent chain at once — instead of 'Waiting for the
        first option-chain snapshot…' until the next live fetch (which can
        be hours away outside market hours). One attempt per symbol/expiry
        switch; skipped the moment a live fetch lands."""
        if not symbol or not expiry:
            return
        key = (symbol, expiry)
        with self.lock:
            if self._bootstrap_key != key:     # new target → try immediately
                self._bootstrap_key = key
                self._bootstrap_last_try = 0.0
            if (self._bootstrap_ok or not self.flow_data.empty
                    or self.symbol != symbol or self.expiry != expiry):
                return
            # An empty DB is often TEMPORARY — the SQLite file is typically
            # copied in AFTER the app was launched, and the first stored
            # snapshot may be minutes away. Latching "attempted once, never
            # again" kept such installs on 'Waiting for the first
            # snapshot…' forever. Retry quietly instead.
            if time.time() - self._bootstrap_last_try < BOOTSTRAP_RETRY_SECONDS:
                return
            self._bootstrap_last_try = time.time()
        try:
            prev_ts, prev, db_spot, _ = self._load_prev_chain(symbol, expiry)
        except Exception as exc:
            logger.warning("Bootstrap read failed: %s", exc)
            return
        if prev is None or prev.empty or not db_spot:
            return
        if "chg_oi" not in prev.columns:
            prev["chg_oi"] = 0.0               # stored rows don't carry it
        df = prev[["strike", "iv", "oi", "chg_oi", "volume", "ltp", "type"]]
        try:
            ts_dt = datetime.fromisoformat(prev_ts)
        except (TypeError, ValueError):
            return
        with self.lock:
            if (self.symbol != symbol or self.expiry != expiry
                    or not self.flow_data.empty):
                return                          # a live fetch already won
            self.flow_data    = df
            self.spot_price   = db_spot
            self.last_updated = ts_dt        # pill honestly shows data age
            self.last_change  = ts_dt
            self.last_fp      = None         # next live fetch re-decides
            self._bootstrap_ok = True        # seeded — stop retrying
            self.data_version += 1           # wake the UI watcher
        logger.info("[%s %s] UI seeded from stored snapshot %s",
                    symbol, expiry, prev_ts)

    def _load_prev_chain(self, symbol, expiry
                         ) -> Tuple[Optional[str], pd.DataFrame, float, float]:
        """Last stored snapshot: (timestamp, rows, its spot, its PCR).
        The spot/PCR let the interval summary survive an app restart —
        the in-memory prev_spot/prev_pcr are zeroed on every restart."""
        with self._db() as conn:
            row = conn.execute(
                "SELECT MAX(timestamp) FROM option_chain WHERE symbol=? AND expiry=?",
                (symbol, expiry)).fetchone()
            if not row or not row[0]:
                return None, pd.DataFrame(), 0.0, 0.0
            # FIX: chg_oi is selected too — the bootstrap path used to
            # hardcode 0.0, so the 'Daily Δ OI (exchange)' chart showed
            # false zeros after any restart
            df = pd.read_sql(
                "SELECT strike, type, iv, oi, chg_oi, volume, ltp "
                "FROM option_chain "
                "WHERE symbol=? AND expiry=? AND timestamp=?",
                conn, params=(symbol, expiry, row[0]))
            agg = conn.execute(
                "SELECT spot, pcr FROM snap_agg WHERE symbol=? AND expiry=? AND ts=?",
                (symbol, expiry, row[0])).fetchone()
            db_spot = float(agg[0]) if agg and agg[0] is not None else 0.0
            db_pcr  = float(agg[1]) if agg and agg[1] is not None else 0.0
            if not db_spot:
                # very old DBs may miss the snap_agg row — fall back to the
                # per-row spot_price stored alongside the chain itself,
                # otherwise the seeder would discard perfectly good rows
                srow = conn.execute(
                    "SELECT spot_price FROM option_chain "
                    "WHERE symbol=? AND expiry=? AND timestamp=? "
                    "AND spot_price IS NOT NULL LIMIT 1",
                    (symbol, expiry, row[0])).fetchone()
                db_spot = float(srow[0]) if srow and srow[0] is not None else 0.0
            return row[0], df, db_spot, db_pcr

    # ── FIX #20: recent-fingerprint memory per (symbol|expiry) ─────────
    def _remember_fp(self, symbol: str, expiry: str, fp: str):
        """Record a fingerprint we have STORED — the oscillation guard's
        memory. A later fetch matching any remembered fp (but not the
        last stored one) is an NSE cache flip-flop, not news."""
        key = f"{symbol}|{expiry}"
        ring = self._recent_fps.get(key)
        if ring is None:
            while len(self._recent_fps) >= 16:   # bound tracked targets
                self._recent_fps.pop(next(iter(self._recent_fps)))
            ring = self._recent_fps[key] = deque(maxlen=RECENT_FP_WINDOW)
        if fp not in ring:
            ring.append(fp)

    def _fp_is_recent(self, symbol: str, expiry: str, fp: str) -> bool:
        return fp in self._recent_fps.get(f"{symbol}|{expiry}", ())

    def _detect_events(self, prev: pd.DataFrame, new: pd.DataFrame,
                       spot: float) -> List[Dict]:
        if prev is None or prev.empty:
            return []
        merged = new.merge(prev, on=["strike", "type"], suffixes=("_new", "_prev"))
        # FIX #21: a whole-chain OI flip with frozen premiums AND frozen
        # volumes is a data revision, not trading. Real positioning changes
        # require traded volume (every contract opened/closed IS a trade)
        # and move premiums. NSE serving a different cached copy produced
        # exactly this signature off-hours: mirror-image event storms with
        # Prem +0.0% on every row, repeating every poll.
        if _looks_like_data_revision(merged):
            logger.warning("Suppressed data-revision flip — %d rows changed "
                           "OI with premiums & volumes frozen", len(merged))
            return []
        events: List[Dict] = []
        for r in merged.itertuples(index=False):
            prev_oi  = float(r.oi_prev  or 0)
            new_oi   = float(r.oi_new   or 0)
            prev_ltp = float(r.ltp_prev or 0)
            new_ltp  = float(r.ltp_new  or 0)
            prev_vol = float(r.volume_prev or 0)
            new_vol  = float(r.volume_new  or 0)

            d_oi  = new_oi - prev_oi
            # signed — NSE occasionally revises cumulative volume DOWN;
            # the old max(0, …) clamp silently hid those revisions
            d_vol = new_vol - prev_vol
            d_pct = ((new_ltp - prev_ltp) / prev_ltp * 100) if prev_ltp > 0 else 0.0
            rel = d_oi / prev_oi if prev_oi > 0 else math.inf

            sig = (abs(d_oi) >= ABS_FLOOR
                   or (prev_oi > 0 and abs(rel) >= REL_FLOOR
                       and abs(d_oi) >= REL_MIN_ABS))
            if not sig or d_oi == 0:
                continue

            avol = abs(d_vol)
            # OI-lag signature (OI moved, volume unchanged) is a REAL NSE
            # refresh pattern this app deliberately captures — it must not
            # be scored as low-confidence noise
            oi_lag   = (d_vol == 0 and d_oi != 0)
            vol_ok   = avol >= abs(d_oi) * 0.8
            vol_weak = avol < abs(d_oi) * 0.5
            conf = (0.9 if vol_ok
                    else 0.4 if (vol_weak and not oi_lag)
                    else 0.65)
            cls, note = classify_event(d_oi, d_pct, prev_oi, new_oi,
                                       r.type, spot, r.strike)
            events.append({
                "strike": float(r.strike), "side": r.type,
                "d_oi": d_oi, "d_vol": d_vol, "d_ltp_pct": round(d_pct, 2),
                "prev_oi": prev_oi, "new_oi": new_oi,
                "prev_ltp": prev_ltp, "new_ltp": new_ltp,
                "prem_impact": d_oi * new_ltp,
                "classification": cls, "confidence": conf, "note": note,
            })
        return events


# ═══════════════════════════════ CACHED DB QUERIES (UI) ═══════════════════════════════
@st.cache_data(ttl=30)
def load_snapshot_times(symbol, expiry, data_version=None):
    # data_version: cache-key only — the interval charts must see a newly
    # stored snapshot in the SAME rerun that reveals the events it minted;
    # ttl-only caching is what let the charts trail the events table
    try:
        with _ui_db() as conn:
            rows = pd.read_sql(
                "SELECT DISTINCT timestamp FROM option_chain "
                "WHERE symbol=? AND expiry=?", conn, params=(symbol, expiry))
        if rows.empty:
            return []
        parsed = pd.to_datetime(rows["timestamp"])
        return sorted(zip(rows["timestamp"].tolist(), parsed.tolist()),
                      key=lambda p: p[1])
    except (sqlite3.Error, pd.errors.DatabaseError, ValueError):
        return []


def pick_snapshot(pairs, target):
    if not pairs:
        return None, None
    target = target.replace(tzinfo=None)
    eligible = [p for p in pairs if p[1] <= target]
    return eligible[-1] if eligible else pairs[0]


@st.cache_data(ttl=30)
def load_past_snapshot(symbol, expiry, timestamp_raw, lo, hi,
                       data_version=None):
    # data_version: cache-key only — busts alongside load_snapshot_times
    # so the charts never diff against a stale baseline after a new poll
    query = ("SELECT strike, type, iv, oi, volume, ltp FROM option_chain "
             "WHERE symbol=? AND expiry=? AND timestamp=? AND strike BETWEEN ? AND ?")
    try:
        with _ui_db() as conn:
            df = pd.read_sql(query, conn,
                             params=(symbol, expiry, timestamp_raw, lo, hi))
    except (sqlite3.Error, pd.errors.DatabaseError):
        return _empty_past()
    if df.empty:
        return _empty_past()
    for c in ("strike", "iv", "oi", "volume", "ltp"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


@st.cache_data(ttl=15)
def load_strike_history(symbol, expiry, strike):
    query = ("SELECT timestamp, type, oi, iv, ltp FROM option_chain "
             "WHERE symbol=? AND expiry=? AND strike=? ORDER BY timestamp")
    try:
        with _ui_db() as conn:
            df = pd.read_sql(query, conn, params=(symbol, expiry, float(strike)))
    except (sqlite3.Error, pd.errors.DatabaseError):
        return pd.DataFrame(columns=["timestamp", "type", "oi", "iv", "ltp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    for c in ("oi", "iv", "ltp"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


@st.cache_data(ttl=30)
def load_events(symbol, expiry, limit=200, floor=0, side=None, cls=None,
                sort="latest", data_version=None):
    """data_version is a cache key ONLY — it busts this cache the moment
    the engine stores new data instead of up to ttl=30s later. `sort` and
    `cls` are applied server-side: the old code fetched the latest 200
    rows and sorted/filtered in Python, so 'Biggest |Δ OI|' was only
    biggest-of-the-latest-200, and a type filter could come up empty
    even when matching events existed beyond that window."""
    q = "SELECT * FROM events WHERE symbol=? AND expiry=? AND ABS(d_oi)>=?"
    a = [symbol, expiry, floor]
    if side in ("CE", "PE"):
        q += " AND side=?"
        a.append(side)
    if cls:
        q += " AND classification=?"
        a.append(cls)
    if sort == "biggest":
        q += " ORDER BY ABS(d_oi) DESC, id DESC LIMIT ?"
    else:
        q += " ORDER BY id DESC LIMIT ?"
    a.append(limit)
    try:
        with _ui_db() as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(r) for r in conn.execute(q, a)]
    except sqlite3.Error:
        return []
    return rows


@st.cache_data(ttl=60)
def load_event_stats(symbol, expiry, floor=0, data_version=None):
    # data_version: cache key only — busts alongside load_events
    day = datetime.now(IST).date().isoformat()
    try:
        with _ui_db() as conn:
            conn.row_factory = sqlite3.Row
            rows = list(conn.execute(
                """SELECT classification, COUNT(*) n, SUM(prem_impact) prem
                   FROM events
                   WHERE symbol=? AND expiry=? AND ts LIKE ? AND ABS(d_oi)>=?
                   GROUP BY classification""",
                (symbol, expiry, day + "%", floor)))
    except sqlite3.Error:
        return {}
    return {r["classification"]: {"n": r["n"], "prem": r["prem"] or 0}
            for r in rows}


@st.cache_data(ttl=30)
def load_shorts_flow(symbol, expiry, data_version=None):
    """Today's writer-side events only (NEW_SHORTS + SHORT_COVER), for the
    Shorts Flow tab. data_version is a cache-buster exactly like
    load_events — new data lands, the table refreshes immediately."""
    day = datetime.now(IST).date().isoformat()
    try:
        with _ui_db() as conn:
            conn.row_factory = sqlite3.Row
            rows = list(conn.execute(
                """SELECT * FROM events
                   WHERE symbol=? AND expiry=? AND ts LIKE ?
                     AND classification IN ('NEW_SHORTS', 'SHORT_COVER')
                   ORDER BY id DESC LIMIT 2000""",
                (symbol, expiry, day + "%")))
    except sqlite3.Error:
        return []
    return [dict(r) for r in rows]


@st.cache_data(ttl=30)
def load_shorts_book(symbol, expiry, data_version=None):
    """FULL-expiry writer-side events (NEW_SHORTS + SHORT_COVER), oldest
    first — the raw material for the per-strike tracked short book. Not
    day-filtered on purpose: shorts written on earlier days of this
    expiry are the ones being covered today, so the ledger has to start
    at the first stored event. data_version busts alongside the other
    loaders so the book moves in the same rerun as the event rows."""
    try:
        with _ui_db() as conn:
            conn.row_factory = sqlite3.Row
            rows = list(conn.execute(
                """SELECT id, ts, strike, side, d_oi, classification
                   FROM events
                   WHERE symbol=? AND expiry=?
                     AND classification IN ('NEW_SHORTS', 'SHORT_COVER')
                   ORDER BY id LIMIT 20000""",
                (symbol, expiry)))
    except sqlite3.Error:
        return []
    return [dict(r) for r in rows]


def build_short_book(rows):
    """Per-contract tracked short book, walked chronologically.

    NEW_SHORTS adds Δ OI to that strike's book; SHORT_COVER burns it
    down. Each cover is annotated with how much of the then-open book it
    retired: cov_by_id[id] = {amt, before, pct}. A cover larger than
    the tracked book (pct > 1) means shorts written BEFORE tracking
    began were bought back — reported, not hidden. The open book is
    floored at 0 per strike, never allowed to go negative."""
    book, agg, cov_by_id = {}, {}, {}
    for e in rows:                                   # already id-ordered
        key = (float(e["strike"]), str(e["side"]))
        d_oi = float(e.get("d_oi") or 0.0)
        a = agg.setdefault(key, {"written": 0.0, "covered": 0.0,
                                 "ns": 0, "sc": 0})
        cur = book.get(key, 0.0)
        if e.get("classification") == "NEW_SHORTS":
            book[key] = cur + d_oi
            a["written"] += d_oi
            a["ns"] += 1
        else:                                         # SHORT_COVER, d_oi < 0
            amt = abs(d_oi)
            cov_by_id[e["id"]] = {"amt": amt, "before": cur,
                                  "pct": (amt / cur) if cur > 0 else None}
            book[key] = max(0.0, cur - amt)
            a["covered"] += amt
            a["sc"] += 1
    for a in agg.values():
        a["open"] = max(0.0, a["written"] - a["covered"])
        a["cover_pct"] = ((a["covered"] / a["written"])
                          if a["written"] > 0 else None)
    return agg, cov_by_id


def _cov_note(c):
    """One-line coverage annotation for a SHORT_COVER event row."""
    if not c:
        return None
    amt, before, pct = c["amt"], c["before"], c["pct"]
    if pct is None:
        return (f"covered {fmt_cnt(amt)} — no tracked shorts at this "
                f"strike yet (pre-tracking shorts)")
    if pct > 1.0:
        return (f"covered {fmt_cnt(amt)} of {fmt_cnt(before)} tracked "
                f"({pct:.0%} — rest pre-tracking)")
    return f"covered {fmt_cnt(amt)} of {fmt_cnt(before)} tracked ({pct:.0%})"


def enrich_cover_notes(evs, cov_by_id):
    """Copy event rows and stamp SHORT_COVER notes with the strike-book
    coverage (how much of that strike's tracked shorts this cover
    retired at event time)."""
    out = []
    for e in evs:
        e2 = dict(e)
        if e2.get("classification") == "SHORT_COVER":
            note = _cov_note(cov_by_id.get(e2.get("id")))
            if note:
                base = str(e2.get("note") or "").strip()
                e2["note"] = f"{base} · {note}" if base else note
        out.append(e2)
    return out


@st.cache_data(ttl=60)
def load_iv_history(symbol, expiry, days=30):
    since = (datetime.now(IST).replace(tzinfo=None)
             - timedelta(days=days)).isoformat(timespec="seconds")
    try:
        with _ui_db() as conn:
            df = pd.read_sql(
                "SELECT ts, atm_iv FROM snap_agg WHERE symbol=? AND expiry=? "
                "AND ts>=? AND atm_iv IS NOT NULL ORDER BY ts",
                conn, params=(symbol, expiry, since))
    except (sqlite3.Error, pd.errors.DatabaseError):
        return pd.DataFrame(columns=["ts", "atm_iv"])
    df["atm_iv"] = pd.to_numeric(df["atm_iv"], errors="coerce")
    return df


@st.cache_data(ttl=60)
def load_agg_history(symbol, expiry, hours=72):
    # 72 h (was 8 h) — the rolling 8-hour window hid ALL history whenever
    # the app was opened outside market hours (evenings/weekends)
    since = (datetime.now(IST).replace(tzinfo=None)
             - timedelta(hours=hours)).isoformat(timespec="seconds")
    try:
        with _ui_db() as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(r) for r in conn.execute(
                "SELECT ts,spot,atm_iv,tot_ce_oi,tot_pe_oi,pcr FROM snap_agg "
                "WHERE symbol=? AND expiry=? AND ts>=? ORDER BY ts",
                (symbol, expiry, since))]
    except sqlite3.Error:
        return []
    return rows


@st.cache_data(ttl=60)
def load_day_open(symbol, expiry):
    day = datetime.now(IST).date().isoformat()
    try:
        with _ui_db() as conn:
            row = conn.execute(
                "SELECT spot FROM snap_agg WHERE symbol=? AND expiry=? AND ts LIKE ? "
                "ORDER BY ts LIMIT 1", (symbol, expiry, day + "%")).fetchone()
    except sqlite3.Error:
        return None
    return row[0] if row else None


@st.cache_data(ttl=300)
def load_db_stats():
    out = {}
    try:
        with _ui_db() as conn:
            for t in ("option_chain", "events", "snap_agg"):
                try:
                    out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                except sqlite3.Error:
                    out[t] = 0
    except sqlite3.Error:
        pass
    return out


@st.cache_data(ttl=60)
def events_csv(symbol, expiry):
    try:
        with _ui_db() as conn:
            df = pd.read_sql(
                """SELECT ts,strike,side,d_oi,d_vol,d_ltp_pct,prev_oi,new_oi,
                          prev_ltp,new_ltp,prem_impact,classification,
                          confidence,note FROM events
                   WHERE symbol=? AND expiry=? ORDER BY id""",
                conn, params=(symbol, expiry))
    except (sqlite3.Error, pd.errors.DatabaseError):
        return ""
    return df.to_csv(index=False) if not df.empty else ""


# ═══════════════════════════════ CHART BUILDERS ═══════════════════════════════
def _layout(fig, height, title=""):
    fig.update_layout(template="plotly_dark", height=height,
                      margin=dict(l=10, r=10, t=40 if title else 30, b=10),
                      hovermode="x unified", title_text=title or None,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                  xanchor="right", x=1))
    return fig


def _style(fig, height, x_title="", y_title="", title=""):
    _layout(fig, height, title)
    fig.update_xaxes(gridcolor=GRID_COLOR, title_text=x_title)
    fig.update_yaxes(gridcolor=GRID_COLOR, title_text=y_title)
    return fig


# v2.8 — one strike label per bar (user report: "strike number is not
# easy to identify, can't see for which bar what strike it is"). With a
# plain numeric x-axis plotly only prints ticks at "nice" values
# (24,500 / 25,000) while the bars sit at every REAL strike in the band
# (24,550, 24,600, ...) — so a bar fell between two printed labels and
# nothing on screen said which strike it was. Array-mode ticks pin one
# label at every bar's exact x position instead. Buckets keep the labels
# readable as the sidebar ATM band widens (13 strikes at the default
# ±300 → up to 81 at ±2000; thresholds calibrated for the ~590 px
# half-width chart columns): flat while they fit horizontally, 45°
# diagonal, then vertical, and past 48 strikes every other strike (the
# in-between bars are then read by hover, which always names the strike).
STRIKE_AXIS_MAX_FLAT = 14   # ≤ this many strikes: horizontal labels
STRIKE_AXIS_MAX_DIAG = 24   # ≤ this: 45° diagonal
STRIKE_AXIS_MAX_VERT = 48   # ≤ this: vertical; beyond: every other strike


def _strike_axis(fig, strikes):
    """Pin one x-tick label at every bar's exact strike (v2.8)."""
    s = sorted({float(v) for v in strikes if v == v})   # dedupe + drop NaN
    if not s:
        return fig
    if len(s) <= STRIKE_AXIS_MAX_FLAT:
        angle, step = 0, 1
    elif len(s) <= STRIKE_AXIS_MAX_DIAG:
        angle, step = -45, 1
    elif len(s) <= STRIKE_AXIS_MAX_VERT:
        angle, step = -90, 1
    else:
        angle, step = -90, 2
    tv = s[::step]
    fig.update_xaxes(tickmode="array", tickvals=tv,
                     ticktext=[f"{v:,.0f}" for v in tv],
                     tickangle=angle, tickfont=dict(size=10))
    return fig


def build_oi_bar(df, y, y_title, spot, height=420, tags=False,
                 tag_floor=ACTIVITY_TAG_FLOOR):
    fig = px.bar(df, x="strike", y=y, color="type", barmode="group",
                 color_discrete_map={"CE": CALL_COLOR, "PE": PUT_COLOR})
    if spot:
        fig.add_vline(x=spot, line_dash="dash", line_color=SPOT_COLOR, line_width=1.5)
    # v2.7: activity tag at each bar's outer end — writing / buying /
    # covering / long exit from the OI × premium quadrant. Positive bars
    # get their tag above, negative bars below the tip, so opposite-side
    # bars never collide. Requires the 'act' column from
    # _interval_activity; the other build_oi_bar call sites (plain OI,
    # exchange chg_oi) pass tags=False and are unaffected.
    if tags and "act" in df.columns and not df.empty:
        top = float(df[y].abs().max()) or 1.0
        pad = top * 0.035
        for cls, (emoji, word, color) in ACTIVITY_META.items():
            sub = df[(df["act"] == cls) & (df[y].abs() >= tag_floor)]
            if sub.empty:
                continue
            ends = [v + pad if v > 0 else v - pad for v in sub[y]]
            fig.add_trace(go.Scatter(
                x=sub["strike"], y=ends, mode="text",
                text=[emoji] * len(sub),
                textfont=dict(size=13, color=color),
                textposition="middle center",
                hoverinfo="text",
                hovertext=[f"{word} · OI {v:+,.0f}" for v in sub[y]],
                showlegend=False))
    # v2.8: one strike label under every bar — bars no longer sit
    # between the printed "nice" ticks
    return _strike_axis(_style(fig, height, "Strike", y_title),
                        df["strike"])


def build_iv_figure(piv, spot):
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.09,
        subplot_titles=("IV Smile (CE vs PE)", "IV Skew (Put IV − Call IV)"),
        row_heights=[0.68, 0.32])
    fig.add_trace(go.Scatter(x=piv["strike"], y=piv["CE"], mode="lines+markers",
                             name="Call IV", line=dict(color=CALL_COLOR, width=2.5),
                             marker=dict(size=6)), row=1, col=1)
    fig.add_trace(go.Scatter(x=piv["strike"], y=piv["PE"], mode="lines+markers",
                             name="Put IV", line=dict(color=PUT_COLOR, width=2.5),
                             marker=dict(size=6, symbol="diamond")), row=1, col=1)
    fig.add_trace(go.Bar(x=piv["strike"], y=piv["skew_diff"], name="Skew (PE−CE)",
                         marker_color=[PUT_COLOR if v > 0 else CALL_COLOR
                                       for v in piv["skew_diff"]],
                         opacity=0.85), row=2, col=1)
    for r in (1, 2):
        fig.add_vline(x=spot, line_dash="dash", line_color=SPOT_COLOR,
                      line_width=1.5, row=r, col=1)
    _layout(fig, 460)
    fig.update_xaxes(gridcolor=GRID_COLOR, title_text="Strike", row=2, col=1)
    fig.update_yaxes(gridcolor=GRID_COLOR)
    # v2.8: strikes labeled on the shared bottom axis — applies to both
    # rows, only row 2 shows tick labels
    _strike_axis(fig, piv["strike"])
    return fig


def build_iv_shift_figure(shift_df, spot, title="IV shift", height=320):
    fig = go.Figure()
    for typ, label, color in (("CE", "Call IV shift", CALL_COLOR),
                              ("PE", "Put IV shift", PUT_COLOR)):
        sub = shift_df[shift_df["type"] == typ]
        fig.add_trace(go.Scatter(x=sub["strike"], y=sub["iv_delta"],
                                 mode="lines+markers", name=label,
                                 line=dict(color=color, width=2, dash="dot"),
                                 marker=dict(size=6)))
    fig.add_hline(y=0, line_dash="solid", line_color=GRID_COLOR)
    fig.add_vline(x=spot, line_dash="dash", line_color=SPOT_COLOR, line_width=1.5)
    # v2.8: one strike label per marker — same fix as the ΔOI bars
    return _strike_axis(_style(fig, height, "Strike", "IV change (pts)",
                               title), shift_df["strike"])


def build_combo_figure(ts_df, title, mode, line_color):
    """Per-strike history: OI bar + premium line, or IV line + premium line."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if mode == "oi":
        fig.add_trace(go.Bar(x=ts_df["timestamp"], y=ts_df["oi"],
                             name="Open Interest",
                             marker_color="rgba(120,130,150,0.55)"),
                      secondary_y=False)
        y1 = "OI"
    else:
        fig.add_trace(go.Scatter(x=ts_df["timestamp"], y=ts_df["iv"], name="IV %",
                                 line=dict(color="gray", width=2, dash="dot")),
                      secondary_y=False)
        y1 = "IV (%)"
    fig.add_trace(go.Scatter(x=ts_df["timestamp"], y=ts_df["ltp"], name="Premium",
                             line=dict(color=line_color, width=3)), secondary_y=True)
    fig.update_layout(template="plotly_dark", height=300,
                      margin=dict(l=0, r=0, t=40, b=0), hovermode="x unified",
                      showlegend=False, title_text=title)
    fig.update_yaxes(title_text=y1, gridcolor=GRID_COLOR, secondary_y=False)
    fig.update_yaxes(title_text="Premium (₹)", gridcolor=GRID_COLOR, secondary_y=True)
    return fig


def build_atm_iv_pcr_spot_figure(agg):
    xs = [a["ts"] for a in agg]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.6, 0.4],
                        vertical_spacing=0.07,
                        specs=[[{"secondary_y": True}], [{}]])
    fig.add_trace(go.Scatter(x=xs, y=[a["pcr"] for a in agg], name="PCR",
                             line=dict(color=PCR_COLOR)),
                  row=1, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=xs, y=[a["spot"] for a in agg], name="Spot",
                             line=dict(color=SPOT_COLOR)),
                  row=1, col=1, secondary_y=True)
    fig.add_trace(go.Scatter(x=xs, y=[a["atm_iv"] for a in agg], name="ATM IV %",
                             line=dict(color=PUT_COLOR, dash="dot")), row=2, col=1)
    _layout(fig, 400)
    fig.update_yaxes(title_text="PCR", row=1, col=1, secondary_y=False,
                     gridcolor=GRID_COLOR)
    fig.update_yaxes(title_text="Spot", row=1, col=1, secondary_y=True,
                     gridcolor=GRID_COLOR)
    fig.update_yaxes(title_text="ATM IV %", row=2, col=1, gridcolor=GRID_COLOR)
    fig.update_xaxes(gridcolor=GRID_COLOR)
    return fig


def build_iv_history_figure(iv_df):
    fig = go.Figure(go.Scatter(x=iv_df["ts"], y=iv_df["atm_iv"], name="ATM IV",
                               line=dict(color=PCR_COLOR, width=2)))
    return _style(fig, 280, "", "ATM IV (%)", "ATM IV history (30d)")


# ═══════════════════════════════ DASHBOARD (runs inside st.fragment) ═══════════════════════════════
def _active_symbol() -> str:
    custom = str(st.session_state.get("symbol_custom", "") or "").strip().upper()
    return custom or st.session_state.get("symbol_selectbox", "NIFTY")


def _active_expiry():
    return st.session_state.get("expiry_selectbox")


def _status_pill(symbol, expiry, spot, last_updated):
    status = engine.status()
    fails = status["failures"]
    last_change = status.get("last_change")
    now_naive = datetime.now(IST).replace(tzinfo=None)
    m_open = market_open()

    offhours_polling = not engine.market_hours_only

    if last_updated is None:
        state, color = "⏳ WAITING FOR FIRST SNAPSHOT", "#9A6A00"
    elif fails > 0 and (m_open or offhours_polling):
        state, color = f"⚠️ FETCH ISSUES ({fails} in a row)", "#C2410C"
    elif not m_open:
        # FIX: a closed market is not "stale" — the old fixed 45s
        # threshold was tuned for the 15s market-hours cadence and flagged
        # the 60s off-hours cadence (or a parked poller) as STALE all
        # night, every night
        if offhours_polling:
            state = ("🌙 MARKET CLOSED · polling, event detection paused"
                      if not DETECT_OFFHOURS_EVENTS
                      else "🌙 MARKET CLOSED · off-hours polling ON")
        else:
            state = "🌙 MARKET CLOSED · final data"
        color = TEXT_SUB
    else:
        fetch_age = (now_naive - last_updated).total_seconds()
        if fetch_age > POLL_SECONDS * 3:
            state, color = "🟡 STALE (no fetch)", "#9A6A00"
        elif (last_change is not None and
              (now_naive - last_change).total_seconds() > NSE_STALE_SECONDS):
            mins = int((now_naive - last_change).total_seconds() // 60)
            state, color = f"🟡 NSE DATA STALE ({mins}m)", "#9A6A00"
        else:
            state, color = "🟢 LIVE", TEXT_UP

    tick = f"{last_updated:%H:%M:%S}" if last_updated else "—"
    age_html = ""
    if last_change is not None:
        dage = int((now_naive - last_change).total_seconds() // 60)
        age_html = (f"<span>📉 NSE data age <b>{dage}m</b></span>")
    if m_open:
        sess = "market open"
    else:
        sess = ("market closed · off-hours polling ON"
                if offhours_polling else "market closed")
    # FIX: symbol (free-typed in the sidebar) is embedded into this HTML —
    # escape it, or a crafted "symbol" executes script in the page
    esc_sym = html.escape(str(symbol))
    esc_exp = html.escape(str(expiry))
    return (
        "<div style='display:flex;flex-wrap:wrap;gap:1.2rem;align-items:center;"
        "padding:0.55rem 1rem;border:1px solid #D9DEE5;border-radius:10px;"
        "background:#F8FAFC;color:#1F2937;font-size:0.92rem;"
        "margin-bottom:0.6rem;'>"
        f"<span style='font-weight:700;color:{color};'>{state}</span>"
        f"<span>📌 <b>{esc_sym}</b> · expiry <b>{esc_exp}</b></span>"
        f"<span>🕒 last tick <b>{tick}</b></span>"
        f"{age_html}"
        f"<span>💲 spot <b style='color:{SPOT_COLOR};'>{spot:,.2f}</b></span>"
        f"<span style='margin-left:auto;color:#64748B;'>poll {POLL_SECONDS}s · {sess}</span>"
        "</div>")


def _events_table(evs: List[Dict], show_detail: bool, height_cap: int = 420,
                 compact: bool = False):
    """The OI events table rendered as plain scoped HTML instead of
    st.dataframe + Styler. compact=True tightens fonts, padding and the
    note column so the table fits its half of the side-by-side grid."""
    if not evs:
        return

    head = ("<tr><th>Time</th><th>Contract</th><th>Signal</th><th>Δ OI</th>"
            "<th>Prem</th>"
            + ("<th>Δ Vol</th><th>Conf</th>" if show_detail else "")
            + "<th>Note</th></tr>")

    body_rows = []
    for e in evs:
        cls   = str(e.get("classification", ""))
        side  = str(e.get("side", ""))
        d_oi  = float(e.get("d_oi") or 0)
        prem  = float(e.get("d_ltp_pct") or 0)
        sign  = event_sign(cls, side)
        emoji = SIGN_EMOJI.get(sign, "⚪")
        label = CLASS_META.get(cls, {}).get("label", cls)

        up_dn = "d-up" if d_oi > 0 else ("d-dn" if d_oi < 0 else "")
        prem_dn = "d-up" if prem > 0 else ("d-dn" if prem < 0 else "")
        cells = [
            f"<td>{str(e.get('ts', ''))[11:19]}</td>",
            f"<td class='{'t-ce' if side == 'CE' else 't-pe'}'>"
            f"{float(e.get('strike') or 0):,.0f} {side}</td>",
            f"<td><span class='pill p-{sign}'>{emoji} {label}</span></td>",
            f"<td class='{up_dn}'>{signed_cnt(d_oi)}</td>",
            f"<td class='{prem_dn}'>{prem:+.1f}%</td>",
        ]
        if show_detail:
            conf = float(e.get("confidence") or 0)
            cells.append(f"<td>{fmt_cnt(float(e.get('d_vol') or 0))}</td>")
            cells.append(f"<td class='conf'>{conf:.0%}</td>")
        note = str(e.get("note", "")) or "—"
        cells.append(f"<td class='note'>{note}</td>")
        body_rows.append(f"<tr class='r-{sign}'>" + "".join(cells) + "</tr>")

    css = (
        "<style>"
        ".oievt{overflow-y:auto;border:1px solid #D9DEE5;border-radius:10px;"
        "background:#FFFFFF;}"
        ".oievt table{width:100%;border-collapse:collapse;font-size:14.5px;"
        "line-height:1.4;color:#1F2937;font-variant-numeric:tabular-nums;}"
        ".oievt th{position:sticky;top:0;background:#1F2937;color:#FFFFFF;"
        "font-weight:600;font-size:12.5px;letter-spacing:.03em;"
        "padding:8px 12px;text-align:left;white-space:nowrap;z-index:2;}"
        ".oievt td{padding:8px 12px;border-top:1px solid #EDF0F3;"
        "white-space:nowrap;vertical-align:middle;}"
        ".oievt td.note{white-space:normal;min-width:240px;color:#4B5563;"
        "font-size:13px;}"
        ".oievt td.conf{color:#4B5563;}"
        ".oievt tr.r-bull{background:#E9F7EF;}"
        ".oievt tr.r-bear{background:#FDECEA;}"
        ".oievt tr.r-info{background:#EAF1FD;}"
        ".oievt tr.r-warn{background:#FFF6DF;}"
        ".oievt .pill{display:inline-block;padding:3px 10px;"
        "border-radius:999px;color:#FFFFFF;font-weight:600;"
        "font-size:12.5px;line-height:1.25;white-space:nowrap;}"
        ".oievt .p-bull{background:#0B6E4F;}"
        ".oievt .p-bear{background:#B3261E;}"
        ".oievt .p-info{background:#0B57D0;}"
        ".oievt .p-warn{background:#9A6A00;}"
        ".oievt .t-ce{color:#0B57D0;font-weight:700;}"
        ".oievt .t-pe{color:#B3261E;font-weight:700;}"
        ".oievt .d-up{color:#0B6E4F;font-weight:700;}"
        ".oievt .d-dn{color:#B3261E;font-weight:700;}"
        + (".oievt.cmp{overflow-x:auto;}"
           ".oievt.cmp table{font-size:13px;}"
           ".oievt.cmp th{padding:7px 8px;font-size:12px;}"
           ".oievt.cmp td{padding:6px 8px;}"
           ".oievt.cmp td.note{min-width:118px;font-size:12px;}"
           if compact else "")
        + "</style>")
    # v2.5 fix: the opening tag lost its '>' in the v2.4 compact-mode
    # rewrite, which swallowed the <style> block into the div tag and
    # leaked the raw CSS onto the page as text.
    html = (f"<div class='oievt{' cmp' if compact else ''}' "
            f"style='max-height:{int(height_cap)}px'>"
            + css
            + f"<table><thead>{head}</thead><tbody>{''.join(body_rows)}"
              f"</tbody></table></div>")
    st.markdown(html, unsafe_allow_html=True)


def _short_book_table(agg, height_cap=330, compact=False):
    """Tracked short book by strike — how much is still open vs already
    bought back. agg: {(strike, side): {written, covered, open, ...}}
    from build_short_book. compact=True tightens it for half-width
    (side-by-side) placement. Returns True when a table was rendered."""
    rows = sorted(((k, a) for k, a in agg.items()
                   if (a["written"] + a["covered"]) > 0),
                  key=lambda ka: (ka[1]["open"], ka[1]["written"]),
                  reverse=True)[:12]
    if not rows:
        return False
    tot_w = sum(a["written"] for a in agg.values())
    tot_c = sum(a["covered"] for a in agg.values())
    tot_o = sum(a["open"] for a in agg.values())

    body = []
    for (strike, side), a in rows:
        pct = a["cover_pct"]
        pct_txt = f"{pct:.0%}" if pct is not None else "—"
        bar_w = min(100.0, (pct or 0.0) * 100)
        body.append(
            "<tr>"
            f"<td class='l {'t-ce' if side == 'CE' else 't-pe'}'>"
            f"{strike:,.0f} {side}</td>"
            f"<td class='d-dn'>{signed_cnt(a['written'])}</td>"
            f"<td class='d-up'>{fmt_cnt(a['covered'])}</td>"
            f"<td><b>{fmt_cnt(a['open'])}</b></td>"
            f"<td>{pct_txt}</td>"
            f"<td class='sbk-bar'><span style='width:{bar_w:.0f}%'></span></td>"
            "</tr>")

    css = (
        "<style>"
        ".sbk{overflow-y:auto;border:1px solid #D9DEE5;border-radius:10px;"
        "background:#FFFFFF;}"
        ".sbk table{width:100%;border-collapse:collapse;font-size:14.5px;"
        "line-height:1.4;color:#1F2937;font-variant-numeric:tabular-nums;}"
        ".sbk th{position:sticky;top:0;background:#1F2937;color:#FFFFFF;"
        "font-weight:600;font-size:12.5px;letter-spacing:.03em;"
        "padding:8px 12px;text-align:right;white-space:nowrap;z-index:2;}"
        ".sbk th.l{text-align:left;}"
        ".sbk td{padding:8px 12px;border-top:1px solid #EDF0F3;"
        "text-align:right;white-space:nowrap;}"
        ".sbk td.l{text-align:left;}"
        ".sbk .t-ce{color:#0B57D0;font-weight:700;}"
        ".sbk .t-pe{color:#B3261E;font-weight:700;}"
        ".sbk .d-up{color:#0B6E4F;font-weight:700;}"
        ".sbk .d-dn{color:#B3261E;font-weight:700;}"
        ".sbk .sbk-bar{width:140px;}"
        ".sbk .sbk-bar span{display:block;height:9px;border-radius:5px;"
        "background:#0B6E4F;}"
        + (".sbk.cmp{overflow-x:auto;}"
           ".sbk.cmp table{font-size:13px;}"
           ".sbk.cmp th{padding:7px 8px;font-size:12px;}"
           ".sbk.cmp td{padding:6px 8px;}"
           ".sbk.cmp .sbk-bar{width:90px;}"
           if compact else "")
        + "</style>")
    head = ("<tr><th class='l'>Contract</th><th>✍️ Written</th>"
            "<th>🚀 Covered</th><th>Book open</th><th>% covered</th>"
            f"<th style='width:{90 if compact else 140}px'>progress</th>"
            "</tr>")
    # v2.5 fix: same missing-'>' defect as _events_table — the <style>
    # block belongs INSIDE the div, after its opening tag closes.
    html = (f"<div class='sbk{' cmp' if compact else ''}' "
            f"style='max-height:{int(height_cap)}px'>"
            + css
            + f"<table><thead>{head}</thead><tbody>{''.join(body)}"
              f"</tbody></table></div>")
    st.markdown(html, unsafe_allow_html=True)
    pct_all = (tot_c / tot_w) if tot_w > 0 else None
    st.caption(
        "tracked since the first stored event for this expiry · "
        f"Σ written {fmt_cnt(tot_w)} · Σ covered {fmt_cnt(tot_c)}"
        + (f" ({pct_all:.0%})" if pct_all is not None else "")
        + f" · book still open {fmt_cnt(tot_o)} — a cover larger than the "
          "book retired shorts written before tracking began")
    return True


@st.cache_data(ttl=10)
def _db_inventory():
    """What the local DB actually contains — powers the honest empty-state."""
    try:
        with _ui_db() as conn:
            total  = conn.execute(
                "SELECT COUNT(*) FROM option_chain").fetchone()[0]
            newest = conn.execute(
                "SELECT MAX(timestamp) FROM option_chain").fetchone()[0]
            per    = conn.execute(
                "SELECT symbol, COUNT(DISTINCT expiry) FROM option_chain "
                "GROUP BY symbol").fetchall()
        return {"total": total, "newest": newest,
                "per_symbol": {s: n for s, n in per}}
    except Exception:
        return {"total": 0, "newest": None, "per_symbol": {}}


def _render_empty_state(engine, symbol, expiry):
    """An empty dashboard must not be a dead-end."""
    inv = _db_inventory()
    db_ref = f"`{DB_PATH}`"
    newest = inv["newest"]
    if inv["total"] and newest:
        avail = " · ".join(f"**{s}** ({n} exp.)"
                           for s, n in sorted(inv["per_symbol"].items()))
        if engine.market_hours_only and not market_open():
            st.info(
                "🌙 Market is closed — the poller is idle and resumes next "
                "session.\n\n"
                f"Stored history IS available (newest snapshot `{newest}`): "
                f"{avail}. The dashboard stays empty until the symbol/expiry "
                f"selection matches a stored chain — switch it in the "
                f"sidebar.")
        else:
            st.info(
                f"⏳ Waiting for the first option-chain snapshot for "
                f"**{symbol} / {expiry}** (polling every {POLL_SECONDS}s)…\n\n"
                f"The local DB already holds data — newest snapshot "
                f"`{newest}` for: {avail}. If that doesn't match the "
                f"selection above, switch symbol/expiry in the sidebar.\n\n"
                f"DB in use: {db_ref}")
        return
    if engine.market_hours_only and not market_open():
        st.info("🌙 Market is closed — the poller is idle and will resume "
                "next session.")
    else:
        st.info(f"⏳ Waiting for the first option-chain snapshot "
                f"(polling every {POLL_SECONDS}s)…")
    st.info(
        f"📂 No stored history found at {db_ref} yet.\n\n"
        f"To restore old data: **close this app**, copy your previous "
        f"`options_history.db` (plus its `-wal` / `-shm` sidecar files, "
        f"if present) into that exact folder, then reopen — DB seeding "
        f"retries automatically every {BOOTSTRAP_RETRY_SECONDS}s, no "
        f"restart needed. Note: rows older than {RETENTION_DAYS} days "
        f"(or chains whose expiry has passed) are pruned by design.")


def render_dashboard():
    symbol = _active_symbol()
    expiry = _active_expiry()
    if not symbol or not expiry:
        st.info("Select a symbol and expiry in the sidebar to begin.")
        return

    df, spot, last_updated = engine.snapshot()
    st.markdown(_status_pill(symbol, expiry, spot, last_updated),
                unsafe_allow_html=True)

    if df.empty or spot <= 0:
        _render_empty_state(engine, symbol, expiry)
        return

    band = float(st.session_state.get("atm_band", ATM_BAND_DEFAULT))
    view = df[(df["strike"] >= spot - band) & (df["strike"] <= spot + band)].copy()
    if view.empty:
        st.warning("No strikes inside the ATM band — widen the ATM band slider "
                   "in the sidebar.")
        return

    # ---------------- KPI row ----------------
    pcr_oi, pcr_vol = compute_pcr(df)     # chain-wide PCR — the ATM band is
                                          # a DISPLAY filter, not a stats one;
                                          # band-restricted PCR misclassified
                                          # sentiment vs the 1.2 / 0.7 thresholds
    atm_pcr = compute_atm_pcr(view, spot)
    mp = max_pain(df)
    iv_atm = atm_iv_of(view, spot)
    day_open = load_day_open(symbol, expiry)

    k = st.columns(6)
    k[0].metric("Spot", f"{spot:,.2f}",
                f"{spot - day_open:+,.2f}" if day_open else None)
    k[1].metric("PCR (OI)",  f"{pcr_oi:.2f}"  if pcr_oi  else "–")
    k[2].metric("PCR (Vol)", f"{pcr_vol:.2f}" if pcr_vol else "–")
    k[3].metric("PCR @ ATM", f"{atm_pcr:.2f}" if atm_pcr else "–")
    k[4].metric("Max Pain",  f"{mp:,.0f}"     if mp      else "–")
    k[5].metric("ATM IV",    f"{iv_atm:.1f}%" if iv_atm  else "–")
    sent_txt, _ = pcr_sentiment(pcr_oi)
    st.caption(f"{sent_txt} · neutral zone {PCR_BEARISH}–{PCR_BULLISH} · "
               f"ATM band ±{band:,.0f}")

    # ---------------- lookback merge (for interval ΔOI + IV shift) ----------------
    look_label = st.session_state.get("lookback_select", "Last poll (live)")
    minutes = LOOKBACKS.get(look_label, 0)
    now = datetime.now(IST)

    # v2.3: both snapshot loaders cache-bust on data_version — the
    # interval charts must refresh in the SAME rerun that reveals the
    # events the new snapshot minted, never ttl-seconds behind them
    _dv = engine.status()["data_version"]

    pairs = load_snapshot_times(symbol, expiry, data_version=_dv)
    # only TODAY's snapshots are valid comparison points — without this,
    # "Session Start" resolved to YESTERDAY's final snapshot (no snapshot
    # exists ≤ 09:15 today, so the old fallback picked pairs[0]), and a
    # fresh session showed overnight gaps as "interval Δ OI"
    today_pairs = [p for p in pairs
                   if str(p[0]).startswith(now.date().isoformat())]
    if minutes is None:
        target = now.replace(hour=SESSION_START[0], minute=SESSION_START[1],
                             second=0, microsecond=0).replace(tzinfo=None)
        ts_raw, _ts_dt = (today_pairs[0] if today_pairs else (None, None))
    elif minutes == 0:
        # LIVE interval — baseline is the PREVIOUS stored snapshot: the
        # exact pair the detector just diffed, so the newest event rows
        # and the interval chart are the same numbers at the same time
        target = None
        ts_raw, _ts_dt = (today_pairs[-2] if len(today_pairs) >= 2
                          else (today_pairs[0] if today_pairs
                               else (None, None)))
    else:
        target = (now - timedelta(minutes=minutes)).replace(tzinfo=None)
        ts_raw, _ts_dt = pick_snapshot(today_pairs, target)
    lo, hi = float(view["strike"].min()), float(view["strike"].max())
    past = (load_past_snapshot(symbol, expiry, ts_raw, lo, hi,
                               data_version=_dv)
            if ts_raw else _empty_past())

    merged = view.merge(past, on=["strike", "type"], how="left",
                        suffixes=("", "_past"))
    merged["oi_delta"] = merged["oi"] - merged["oi_past"]
    # a zero IV on either side would fake a full-IV swing — mask to NaN
    merged["iv_delta"] = (merged["iv"] - merged["iv_past"]).where(
        (merged["iv"] > 0) & (merged["iv_past"] > 0))

    tabs = st.tabs(["🌊 OI & IV", "✍️ Shorts Flow", "🚨 All Events", "🗄 History"])

    # ════════════════ TAB 1 — OI & IV (Structure & Smile) ════════════════
    with tabs[0]:
        # -- structure at a glance --
        ce_full = df[(df["type"] == "CE") & (df["oi"] > 0)]
        pe_full = df[(df["type"] == "PE") & (df["oi"] > 0)]
        res = float(ce_full.loc[ce_full["oi"].idxmax(), "strike"]) if not ce_full.empty else None
        sup = float(pe_full.loc[pe_full["oi"].idxmax(), "strike"]) if not pe_full.empty else None
        ce_band = float(view.loc[view["type"] == "CE", "oi"].sum())
        pe_band = float(view.loc[view["type"] == "PE", "oi"].sum())

        h = st.columns(4)
        h[0].metric("Resistance", f"{res:,.0f}" if res else "–",
                    "max CE OI", delta_color="off")
        h[1].metric("Support", f"{sup:,.0f}" if sup else "–",
                    "max PE OI", delta_color="off")
        h[2].metric("CE OI (band)", fmt_cnt(ce_band))
        h[3].metric("PE OI (band)", fmt_cnt(pe_band))

        # -- OI section --
        st.markdown("#### 🌊 Open Interest — where the size sits, and today's move")
        st.caption("Left: current OI by strike · Right: today's OI change (exchange-reported)")
        o1, o2 = st.columns(2)
        with o1:
            st.plotly_chart(build_oi_bar(view, "oi", "Open Interest", spot, 380),
                            width="stretch")
        with o2:
            st.plotly_chart(build_oi_bar(view, "chg_oi", "Daily Δ OI (exchange)",
                                         spot, 380),
                            width="stretch")

        # -- IV section --
        st.markdown("#### 📈 Implied Volatility — smile & skew")
        st.caption("IV smile + skew (PE−CE) across the band")
        # NSE reports IV = 0 for deep/stale quotes — plotting them dives
        # the smile to the floor and explodes the skew at the band edges.
        # Mask zeros → NaN so dropna() removes them.
        piv_src = view.copy()
        piv_src["iv"] = piv_src["iv"].where(piv_src["iv"] > 0)
        piv = piv_src.pivot_table(index="strike", columns="type", values="iv",
                                  aggfunc="mean").reset_index()
        if {"CE", "PE"}.issubset(piv.columns):
            piv = piv.dropna(subset=["CE", "PE"]).copy()
            piv["skew_diff"] = piv["PE"] - piv["CE"]
            if not piv.empty:
                st.plotly_chart(build_iv_figure(piv, spot), width="stretch")
            else:
                st.info("No strikes with both CE & PE IV in the band.")
        else:
            st.info("IV smile needs both CE and PE quotes in the band.")

        # -- strike drilldown (OI + IV together) --
        st.markdown("---")
        st.markdown("#### 🔎 Strike drilldown — OI & IV side by side")
        d_sel, d_view = st.columns([1, 3])
        strikes = sorted(view["strike"].unique())
        with d_sel:
            sel_strike = sel_side = None
            if strikes:
                near = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
                sel_strike = st.selectbox("Strike", strikes, index=near,
                                          key="drill_strike",
                                          format_func=lambda s: f"{s:,.0f}")
                sel_side = st.radio("Side", ("CE", "PE"), key="drill_side",
                                    horizontal=True)
        with d_view:
            if sel_strike and sel_side:
                hist = load_strike_history(symbol, expiry, sel_strike)
                sub = hist[hist["type"] == sel_side].reset_index(drop=True)
                if len(sub) >= 2:
                    # trend label = THIS SESSION only — `sub` can span days
                    # (7-day retention) and cross-day first/last OI/premium
                    # diffs mislabeled the build-up classification
                    sess = sub[sub["timestamp"] >=
                               pd.Timestamp(datetime.now(IST).date())]
                    if len(sess) >= 2:
                        label, color = analyze_trend(sess)
                    else:
                        # falling back to the multi-day frame re-created
                        # the cross-day mislabel this guard exists to fix
                        label, color = "Accumulating today's data…", "gray"
                    st.markdown(
                        f"Trend: <span style='background:#F1F5F9;"
                        f"border:1px solid #E2E8F0;border-radius:6px;"
                        f"padding:2px 10px;color:{color};"
                        f"font-weight:600'>{label}</span>",
                        unsafe_allow_html=True)
                    side_color = CALL_COLOR if sel_side == "CE" else PUT_COLOR
                    c1, c2 = st.columns(2)
                    with c1:
                        st.plotly_chart(
                            build_combo_figure(
                                sub, f"{sel_strike:,.0f} {sel_side} — OI vs premium",
                                "oi", side_color),
                            width="stretch")
                    with c2:
                        st.plotly_chart(
                            build_combo_figure(
                                sub, f"{sel_strike:,.0f} {sel_side} — IV vs premium",
                                "iv", side_color),
                            width="stretch")
                else:
                    st.info("Need ≥ 2 stored snapshots for this strike — "
                            "keep watching.")

    # ════════════════ TAB 2 — Shorts Flow (writers vs unwinding) ════════════════
    with tabs[1]:
        st.caption("Only **✍️ new shorts** (fresh writing) and **🚀 short "
                   "covering** (writers buying back) events, today's "
                   "session — the **Interval Δ OI** chart sits right beside "
                   "the shorts table (its controls sit in the strip above "
                   "the pair; same numbers, same rerun; sidebar ⏱️ "
                   "lookback, **Last poll (live)** keeps chart and table in "
                   "lockstep), with the IV-shift chart beside the per-strike "
                   "**short book**: how much is still open vs already bought "
                   "back. CE writing builds resistance (bearish); PE writing "
                   "builds support (bullish).")

        _dv = engine.status()["data_version"]
        shorts = load_shorts_flow(symbol, expiry, data_version=_dv)
        # v2.3: full-expiry short book (writes add, covers burn down) —
        # powers the per-strike table below and the cover-row annotations
        _agg, _cov_by_id = build_short_book(
            load_shorts_book(symbol, expiry, data_version=_dv))

        ns = [e for e in shorts if e.get("classification") == "NEW_SHORTS"]
        sc = [e for e in shorts if e.get("classification") == "SHORT_COVER"]
        ns_oi = sum(e.get("d_oi") or 0 for e in ns)
        sc_oi = sum(e.get("d_oi") or 0 for e in sc)
        prem  = sum(e.get("prem_impact") or 0 for e in shorts)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("✍️ New shorts today", f"{len(ns)}",
                  f"{signed_cnt(ns_oi)} OI", delta_color="off")
        m2.metric("🚀 Short covering today", f"{len(sc)}",
                  f"{signed_cnt(sc_oi)} OI", delta_color="off")
        m3.metric("Net writing pressure", signed_cnt(ns_oi + sc_oi),
                  ("writers adding" if (ns_oi + sc_oi) >= 0
                   else "writers exiting"), delta_color="off")
        m4.metric("Premium committed (writers)",
                  f"₹{abs(prem) / 1e5:.1f}L",
                  ("written" if prem >= 0 else "unwound"),
                  delta_color="off")

        # -- v2.4 layout: the Interval Δ OI chart sits BESIDE the live
        #    shorts table (user request) — a strike that fires an event
        #    shows the same move as a chart bar in the same glance and
        #    the same rerun. The IV-shift chart moved down beside the
        #    per-strike short book, keeping a 2×2 grid. The sidebar ⏱️
        #    lookback selector still controls both charts.
        #    v2.5: the cumulative writer-flow timeline that used to sit
        #    above this grid was removed (user request).
        #    v2.6: the table's header + filters + count caption moved UP
        #    into the full-width strip below — they used to live inside
        #    the table's grid column, where ~300 px of widgets pushed the
        #    table below the chart, so the chart floated noticeably
        #    ABOVE the table instead of beside it (user report). With the
        #    strip above the grid, chart and table start at the same y. --
        sel = None
        sh_detail = False
        if shorts:
            st.markdown("#### 📋 Shorts events (today)")
            f1, f2, f3, f4 = st.columns([1.1, 1.2, 1.9, 1.3])
            with f1:
                sh_side = st.radio("Show", ("All", "CE", "PE"),
                                   horizontal=True, key="sh_side")
            with f2:
                sh_sort = st.radio("Sort", ("Latest", "Biggest |Δ OI|"),
                                   horizontal=True, key="sh_sort")
            with f3:
                sh_floor = st.slider("Minimum |Δ OI| per contract",
                                     min_value=0, max_value=50_000,
                                     value=0, step=500, key="sh_floor")
            with f4:
                sh_detail = st.checkbox("Δ Vol & confidence columns",
                                        value=False, key="sh_detail")

            sel = [e for e in shorts
                   if abs(e.get("d_oi") or 0) >= sh_floor
                   and sh_side in ("All", e.get("side"))]
            if sh_sort == "Biggest |Δ OI|":
                sel.sort(key=lambda e: abs(e.get("d_oi") or 0),
                         reverse=True)
            else:
                sel.sort(key=lambda e: e.get("id") or 0, reverse=True)
            sel = sel[:300]

            if not sel:
                st.info("No shorts events at this filter level — slide "
                        "the |Δ OI| slider left or wait for writers to "
                        "cross the detection thresholds between "
                        "snapshots.")
            else:
                net = sum(e.get("d_oi") or 0 for e in sel)
                st.caption(f"**{len(sel)}** shorts event(s) · net writer "
                           f"Δ OI **{signed_cnt(net)}**")
                sel = enrich_cover_notes(sel, _cov_by_id)

        cA1, cA2 = st.columns([1.2, 1])
        with cA1:
            interval = merged.dropna(subset=["oi_delta"])
            # v2.7: quadrant tag per bar — writing / buying / covering /
            # long exit, the same 2×2 the detector reads (copy; merged
            # itself stays untouched for the IV-shift chart below)
            interval = _interval_activity(interval)
            if not interval.empty:
                if minutes == 0 and ts_raw:
                    lbl = (f"Δ OI — last poll "
                           f"({ts_raw[11:19]} → latest)")
                elif ts_raw:
                    lbl = f"Δ OI vs {ts_raw[11:19]}"
                else:
                    lbl = "Interval Δ OI"
                # 380 matches the table's height cap beside it — the pair
                # now aligns at top AND bottom edges
                st.plotly_chart(
                    build_oi_bar(interval, "oi_delta", lbl, spot, 380,
                                 tags=True),
                    width="stretch")
                st.caption("bar tags: ✍️ writing · 📈 buying (new longs) · "
                           "🚀 covering · 📉 long exit — OI × premium "
                           f"quadrant, bars ≥ {ACTIVITY_TAG_FLOOR:,} Δ OI; "
                           "hover a tag for detail")
            else:
                st.info("Interval Δ OI appears once a lookback snapshot "
                        "is stored.")
        with cA2:
            if sel:
                _events_table(sel, sh_detail, height_cap=380,
                              compact=True)
            elif shorts:
                st.caption("_no rows at this filter level — adjust the "
                           "filters above to bring rows back_")
            else:
                st.info("No writer activity recorded yet today — new shorts "
                        "and short covering events will appear here (and "
                        "only these) as soon as writers cross the detection "
                        "thresholds between snapshots.")

        cB1, cB2 = st.columns([1.2, 1])
        with cB1:
            iv_shift = merged.dropna(subset=["iv_delta"])
            if not iv_shift.empty:
                ttl_ = ("IV shift — last poll" if minutes == 0
                        else f"IV shift since {look_label.lower()}")
                st.plotly_chart(
                    build_iv_shift_figure(iv_shift, spot, ttl_, height=380),
                    width="stretch")
            else:
                st.info("IV shift appears once a lookback snapshot is stored.")
        with cB2:
            # -- v2.3 per-strike tracked short book (writes add, covers
            #    burn it down — answers "how much of it got covered at
            #    that strike", cumulatively, for every strike with
            #    activity); v2.4 placed beside the IV-shift chart --
            if _agg:
                st.markdown("#### 📐 Short book — open vs covered")
                st.caption("every detected ✍️ write adds to a strike's "
                           "book, every detected 🚀 cover buys part of it "
                           "back — ledger spans the whole expiry, not "
                           "just today")
                _short_book_table(_agg, compact=True)
            else:
                st.caption("_Short book appears once writer events are "
                           "detected._")

    # ════════════════ TAB 3 — All Events (full detector table) ════════════════
    with tabs[2]:
        summary, summary_ts = engine.summary()
        if summary:
            st.markdown("##### Latest interval summary")
            st.info(summary)
            if summary_ts:
                st.caption(f"generated {summary_ts} IST")
        elif last_updated:
            st.caption("No significant OI changes detected in the last "
                       "interval yet.")

        # -- Event Table (Filters + Tinted Table) --
        st.markdown("#### 🚨 Detected events table")

        # 🎚️ variable OI filter (view-only; detection thresholds stay fixed)
        ev_floor = st.slider(
            "Minimum |Δ OI| per contract",
            min_value=0, max_value=50_000, value=0, step=500,
            key="ev_oi_floor",
            help="Slide right to show only the bigger OI moves. "
                 f"(Detector records moves ≥ {ABS_FLOOR:,}, or ≥ "
                 f"{REL_FLOOR:.0%} of existing OI with |Δ OI| ≥ "
                 f"{REL_MIN_ABS:,}; 'mass unwind' needs existing "
                 f"OI ≥ {MASS_UNWIND_MIN_OI:,}.)")

        # ---- filter row: event-type dropdown · side · sort ----
        cls_icon = {"NEW_LONGS": "📈", "SHORT_COVER": "🚀",
                    "NEW_SHORTS": "✍️", "LONG_UNWIND": "📉",
                    "FRESH_BUILDUP": "🌱", "MASS_UNWIND": "🧨"}
        cat_order = ["NEW_LONGS", "SHORT_COVER",      # bullish-flavoured
                     "NEW_SHORTS", "LONG_UNWIND",     # bearish-flavoured
                     "FRESH_BUILDUP", "MASS_UNWIND"]  # specials
        type_labels = {c: f"{cls_icon.get(c, '▫️')} "
                          f"{CLASS_META.get(c, {}).get('label', c)}"
                       for c in cat_order}
        type_labels["ALL"] = "All types"

        f1, f2, f3 = st.columns([2, 2, 2])
        with f1:
            ev_cls = st.selectbox("Event type", ["ALL"] + cat_order, index=0,
                                  key="ev_type",
                                  format_func=lambda c: type_labels.get(c, str(c)))
        with f2:
            ev_side = st.radio("Show", ("All", "CE", "PE"), horizontal=True,
                               key="ev_side")
        with f3:
            ev_sort = st.radio("Sort", ("Latest", "Biggest |Δ OI|"),
                               horizontal=True, key="ev_sort")
        show_detail = st.checkbox("Δ Vol & confidence columns",
                                  value=False, key="ev_detail")

        _dv = engine.status()["data_version"]   # bust the events cache the
                                                 # moment new data lands —
                                                 # ttl alone served rows up
                                                 # to 30s stale
        evs = load_events(symbol, expiry, limit=200, floor=ev_floor,
                          side=None if ev_side == "All" else ev_side,
                          cls=None if ev_cls == "ALL" else ev_cls,
                          sort=("biggest" if ev_sort == "Biggest |Δ OI|"
                                else "latest"),
                          data_version=_dv)

        # v2.3: stamp short-cover rows with how much of that strike's
        # tracked short book they retired at event time
        _bk_rows = load_shorts_book(symbol, expiry, data_version=_dv)
        if _bk_rows:
            evs = enrich_cover_notes(evs, build_short_book(_bk_rows)[1])

        type_txt = type_labels.get(ev_cls, str(ev_cls)).lower()
        st.caption(f"Showing **{len(evs)}** event(s) · |Δ OI| ≥ "
                   f"**{fmt_cnt(ev_floor)}** · {type_txt}"
                   f"{'' if ev_side == 'All' else f' · {ev_side} only'}")

        if not evs:
            st.info("No events at this filter level — change the event type "
                    "or side filter, slide the |Δ OI| slider left, or wait "
                    "for OI moves to cross the detection thresholds between "
                    "snapshots.")
        else:
            net = sum(e.get("d_oi") or 0 for e in evs)
            big = max(evs, key=lambda e: abs(e.get("d_oi") or 0))
            st.caption(f"**{len(evs)}** event(s) · net Δ OI "
                       f"**{signed_cnt(net)}** · biggest "
                       f"**{big['strike']:,.0f} {big['side']}** "
                       f"({signed_cnt(big['d_oi'])})")
            _events_table(evs, show_detail, height_cap=420)

            # category overview (respects the |Δ OI| floor; always shows all
            # detected types so you can see where the action is)
            stats = load_event_stats(symbol, expiry, floor=ev_floor,
                                     data_version=_dv)
            if stats:
                st.markdown(f"##### Today by classification "
                            f"(|Δ OI| ≥ {fmt_cnt(ev_floor)})")
                scol = st.columns(len(stats))
                for col, (cls, d) in zip(scol, stats.items()):
                    col.metric(f"{cls_icon.get(cls, '▫️')} "
                               f"{CLASS_META.get(cls, {}).get('label', cls)}",
                               f"{d['n']}",
                               f"₹{(d['prem'] or 0) / 1e5:+.1f}L prem",
                               delta_color="off")

    # ════════════════ TAB 4 — History (aggregates + DB stats) ════════════════
    with tabs[3]:
        # -- v2.2: the interval ΔOI / IV-shift lookback charts moved into
        #    the Shorts Flow tab; this tab keeps session aggregates --
        agg = load_agg_history(symbol, expiry)
        if agg:
            st.plotly_chart(build_atm_iv_pcr_spot_figure(agg),
                            width="stretch")
        else:
            st.info("Aggregate history (PCR / spot / ATM IV) appears after a "
                    "few snapshots.")
        iv_df = load_iv_history(symbol, expiry)
        if not iv_df.empty:
            st.plotly_chart(build_iv_history_figure(iv_df),
                            width="stretch")
        dbstats = load_db_stats()
        m = st.columns(3)
        m[0].metric("option_chain rows", fmt_cnt(dbstats.get("option_chain")))
        m[1].metric("events rows",       fmt_cnt(dbstats.get("events")))
        m[2].metric("snap_agg rows",     fmt_cnt(dbstats.get("snap_agg")))
        st.caption(f"Retention: {RETENTION_DAYS} days · hourly pruning · "
                   f"duplicate, stale and flip-flopped snapshots skipped "
                   f"by content fingerprint")


# ═══════════════════════════════ APP ═══════════════════════════════
st.set_page_config(page_title="NSE Options Analytics + OI Events",
                   page_icon="⚡", layout="wide")

if not PNSEA_AVAILABLE:
    st.error("Missing dependency: run `pip install pnsea` and restart the app.")
    st.stop()


# ═══════════════════════════════ ENGINE POOL ═══════════════════════════════
MAX_POOLED_ENGINES = 4          # bounds concurrent pollers / NSE sessions
_engine_pool_lock = threading.Lock()


@st.cache_resource
def _engine_pool():
    return {}


def get_engine(symbol: str) -> NiftyOptionEngine:
    """One engine (poller + NSE session) per symbol, LRU-capped.

    FIX: the old single shared engine meant two tabs (or two users) with
    different symbols called set_symbol() on every rerun — perpetual
    state resets, data_version ping-pong and mid-fetch aborts. Per-symbol
    engines keep each view's data alive (A→B→A round-trips are instant),
    while the cap bounds background NSE load."""
    pool = _engine_pool()
    with _engine_pool_lock:
        eng = pool.pop(symbol, None)     # pop + re-insert = LRU recency
        if eng is None:
            eng = NiftyOptionEngine(symbol=symbol)
            eng.start_engine()
        pool[symbol] = eng
        while len(pool) > MAX_POOLED_ENGINES:
            old_sym, old_eng = next(iter(pool.items()))
            try:
                old_eng.stop_engine()
            except Exception:
                pass
            del pool[old_sym]
            logger.info("Evicted pooled engine for %s (cap %d)",
                        old_sym, MAX_POOLED_ENGINES)
        return eng


# -------------------- SIDEBAR --------------------
st.sidebar.title("⚡ Options + OI Events")

_prev_sym = st.session_state.get("symbol_selectbox", "NIFTY")
_default_symbol = _prev_sym if _prev_sym in SYMBOLS else "NIFTY"
picked = st.sidebar.selectbox(
    "Underlying — click and type to search",
    SYMBOLS, index=SYMBOLS.index(_default_symbol), key="symbol_selectbox")
custom = st.sidebar.text_input(
    "Or enter a custom NSE symbol", value="",
    placeholder="e.g. PERSISTENT (blank = use dropdown)",
    key="symbol_custom").strip().upper()
symbol = custom if custom else picked

# a UI symbol change resets the expiry picker (nearest expiry); the
# engine itself keeps its per-symbol state
if symbol != st.session_state.get("_last_symbol"):
    st.session_state._last_symbol = symbol
    st.session_state.pop("expiry_selectbox", None)

# per-symbol engine (LRU-capped pool) — see get_engine()
engine = get_engine(symbol)
# apply the off-hours toggle right away; the sidebar toggle re-applies it
# after it renders. Pooled background engines keep the safe default.
engine.market_hours_only = not st.session_state.get("poll_offhours", True)


@st.cache_data(ttl=300)   # expiries change overnight, not per minute —
                          # each cache miss costs a full option-chain call
def _fetch_expiries_cached(sym):
    return engine.get_expiries(retries=2, delay=1.0, symbol=sym)


def _fetch_expiries(sym):
    """Cached — but a FAILED (empty) fetch is never cached. A transient
    NSE hiccup used to lock the sidebar into 'No expiries' for 5 minutes."""
    out = _fetch_expiries_cached(sym)
    if not out:
        _fetch_expiries_cached.clear()
    return out


expiries = _fetch_expiries(symbol)
if not expiries:
    # NSE unreachable (after hours, weekend, hiccup)? Fall back to the
    # expiries that exist in the local DB so stored history stays
    # reachable instead of halting the whole page.
    expiries = _db_expiries_cached(symbol)
    if expiries:
        st.sidebar.warning("NSE expiry list unavailable — using the "
                           f"{len(expiries)} expiry stored in the local DB.")
if not expiries:
    st.sidebar.error(f"No expiries returned for {symbol}. "
                     "Check the symbol spelling or try again shortly.")
    if st.sidebar.button("🔁 Retry"):
        # FIX: _fetch_expiries is a plain function — only the cached
        # variants expose .clear(); the old call raised AttributeError
        # every time the button was clicked
        _fetch_expiries_cached.clear()
        _db_expiries_cached.clear()
        st.rerun()
    st.stop()

expiry = st.sidebar.selectbox("Select Expiry", expiries, index=0,
                              key="expiry_selectbox")
if expiry != engine.expiry:
    engine.set_expiry(expiry)

st.sidebar.markdown("---")
st.sidebar.subheader("⏱️ Comparison lookback")
st.sidebar.selectbox("Compare current vs:", list(LOOKBACKS), index=0,
                     key="lookback_select",
                     help="Feeds the Interval Δ OI and IV-shift charts on "
                          "the Shorts Flow tab. 'Last poll (live)' diffs "
                          "against the previous stored snapshot — the "
                          "exact interval the detector just processed — "
                          "so the charts move in the same rerun as the "
                          "events table (no lag).")

st.sidebar.subheader(
    f"🎯 ATM band (±{st.session_state.get('atm_band', ATM_BAND_DEFAULT):,.0f} pts)")
st.sidebar.slider("Show strikes within ±points of spot",
                  min_value=ATM_BAND_MIN, max_value=ATM_BAND_MAX,
                  value=ATM_BAND_DEFAULT, step=50, key="atm_band",
                  help="Charts, KPIs and the drilldown show only strikes "
                       "inside this band around spot.")

st.sidebar.markdown("---")
auto_refresh = st.sidebar.toggle("Live updates — only on new NSE data",
                                 value=True, key="auto_refresh")
if not auto_refresh:
    st.sidebar.button("🔄 Refresh now", type="primary")

st.sidebar.toggle(f"🌙 Poll outside market hours (every {OFFHOURS_POLL_SECONDS}s)",
                  value=True, key="poll_offhours",
                  help="Fetch the chain even when the market is closed — "
                       "captures the day's final snapshot and lets you test "
                       "on weekends. Identical snapshots are never stored "
                       "twice, cache flip-flops are skipped, and event "
                       "detection pauses while the market is closed (no "
                       "trading = no real OI events).")

# engine default (MARKET_HOURS_ONLY) applies until the toggle renders;
# afterwards the toggle wins on every rerun
engine.market_hours_only = not st.session_state.get("poll_offhours", True)

st.sidebar.markdown("---")
st.sidebar.download_button("⬇️ Events CSV", data=events_csv(symbol, expiry),
                           file_name=f"events_{symbol}_{expiry}.csv",
                           mime="text/csv", width="stretch")
_hstat = engine.status()
_health = (f"🔗 NSE session {_hstat['session_age_min']}m · "
           f"session rebuilds {_hstat['rebuilds']}"
           + (f" · ⚠️ poller heartbeat {_hstat['heartbeat_age']}s"
              if _hstat["heartbeat_age"] > 90 else ""))
st.sidebar.caption(_health)
st.sidebar.caption(f"Poller {POLL_SECONDS}s (market) / {OFFHOURS_POLL_SECONDS}s "
                   f"(off-hours) · NSE session "
                   f"{SESSION_START[0]:02d}:{SESSION_START[1]:02d}–"
                   f"{SESSION_END[0]:02d}:{SESSION_END[1]:02d} IST · "
                   f"UI re-renders only on new NSE data "
                   f"(checked every {REFRESH_SECONDS}s) · retention {RETENTION_DAYS}d")

# -------------------- MAIN AREA --------------------
st.title("NSE Options Analytics + OI Event Detector")
st.caption("Live option-chain analytics, OI & IV structure and OI event "
           "detection · data: NSE via pnsea · stored locally in SQLite (WAL)")

# -------------------- LIVE UPDATES (only on new NSE data) --------------------
# The old design re-rendered the dashboard every REFRESH_SECONDS whether or
# not anything changed (constant flicker + wasted CPU). Now the dashboard
# renders on full runs, and a tiny SILENT watcher fragment wakes every
# REFRESH_SECONDS to compare the engine's data version + failure count with
# what is on screen. It triggers a full app rerun ONLY when something actually
# changed — no new NSE data → no re-render at all.
render_dashboard()

_s = engine.status()
st.session_state._ui_sig = (_s["data_version"], _s["failures"])

_frag = getattr(st, "fragment", None)
if _frag and auto_refresh:
    def _data_watcher():
        try:
            _s = engine.status()
            _sig = (_s["data_version"], _s["failures"])
        except Exception:
            return
        if _sig != st.session_state.get("_ui_sig"):
            st.session_state._ui_sig = _sig
            try:
                st.rerun(scope="app")       # full rerun → fresh dashboard
            except TypeError:               # very old Streamlit
                st.rerun()
    # ⚠️ The decorated fragment must actually be CALLED — its run_every
    # timer only arms when the fragment executes during a script run
    # (verified in the Streamlit 1.46 source: the auto_rerun ForwardMsg is
    # enqueued inside the wrapper's __call__, right before it runs the
    # fragment body). Defining the watcher without calling it left the
    # timer dead: the poller kept logging new snapshots while the
    # dashboard sat frozen on old data until a manual interaction.
    _data_watcher = _frag(run_every=REFRESH_SECONDS)(_data_watcher)
    _data_watcher()
elif not _frag and auto_refresh:
    st.caption("ℹ️ Auto-on-change updates need Streamlit ≥ 1.37 — "
               "use the 🔄 Refresh now button otherwise.")

with st.expander("ℹ️ How to read this dashboard"):
    st.markdown(
        f"""
- **Green = calls / bullish**, **red = puts / bearish**, **gold = spot** —
  consistent across every chart.
- **Strike axes** — every bar carries its own strike label right under
  it, at the bar's exact position; widen the ATM band and the labels
  rotate (then step) to stay readable — hover a bar for its exact strike
  anyway.
- **Resistance / Support** — strikes carrying the largest CE / PE OI.
- **PCR** ≥ {PCR_BULLISH} → put-heavy (bullish bias); ≤ {PCR_BEARISH} →
  call-heavy (bearish bias).
- **Max Pain** — strike where option writers lose the least at expiry;
  price often gravitates there into the close.
- **OI & IV tab** — OI distribution, daily & interval ΔOI, IV smile/skew
  and IV shift, plus a per-strike drilldown showing OI and IV against
  premium for the whole session.
- **Shorts Flow tab** — writer-side activity ONLY (✍️ new shorts + 🚀
  short covering): today's KPIs (counts, net OI, premium committed), a
  filter strip, then a side-by-side pair — the **interval ΔOI chart
  right next to the shorts table**, each bar tagged with what the flow
  is: **✍️ writing** (OI up, premium down), **📈 buying** (OI up,
  premium up), **🚀 covering** (OI down, premium up), **📉 long exit**
  (OI down, premium down) (sidebar ⏱️ lookback; **Last poll (live)**
  diffs the
  exact interval the detector just processed, so a strike that just
  showed up in the events table shows the same number in the chart
  instantly), and below it the IV-shift chart beside the **short book
  by strike** (every write adds, every cover buys back — “% covered” =
  share of the strike's tracked shorts already retired); cover rows in
  the table read “covered X of Y tracked (Z%)”.
- **All Events tab** — the full events tinted table with the usual
  type/side/sort filters. Row tints are side-aware: 🟢 bullish, 🔴 bearish,
  🔵 informational, 🟠 warning.
- **Stale data & duplicates** — every fetch is fingerprinted; snapshots
  identical to the last one (NSE caches its chain and refreshes it at
  irregular intervals) are skipped, and nothing is ever stored twice.
  The status pill shows the **NSE data age** and flags it stale if the
  exchange hasn't refreshed for {NSE_STALE_SECONDS // 60}+ minutes during
  market hours.
- **Off-hours polling** — the sidebar toggle lets the poller run outside
  market hours at a gentle {OFFHOURS_POLL_SECONDS}s cadence. Duplicates and
  cache flip-flops are never stored, and event detection pauses while
  the market is closed — an OI "change" between two closed-market
  fetches is NSE serving a different cached copy of the final chain,
  not trading.
""")