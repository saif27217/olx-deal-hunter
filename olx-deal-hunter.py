#!/usr/bin/env python3
"""OLX Hyderabad Mac deals (Mini/Studio/MacBook) — Firecrawl + Google Doc + email."""

import json, os, sys, re, time, base64
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MCP_ENDPOINT = "https://connect.composio.dev/mcp"
TOKEN_PATH = os.path.expanduser("~/.hermes/mcp-tokens/composio.json")
USER_EMAIL = "drsaif.biochemistry@gmail.com"
DATA_DIR = Path.home() / ".hermes" / "data"
SEEN_FILE = DATA_DIR / "olx-mac-deals-seen.json"

OLX_API = "https://www.olx.in/api/relevance/v4/search?location=4058526&platform=web-desktop&limit=40"

# Broader queries to catch more deals
QUERIES = [
    # Mac Mini variants
    "mac mini", "mac mini m4", "mac mini m4 pro", "mac mini m4 max",
    "mac mini m2", "mac mini m2 pro", "mac mini m2 max",
    "mac mini m1", "mac mini m1 pro", "mac mini m1 max",
    "mac mini 64gb", "mac mini 32gb", "mac mini 24gb",
    # Mac Studio variants
    "mac studio", "mac studio m2", "mac studio m2 max", "mac studio m2 ultra",
    "mac studio m3", "mac studio 64gb", "mac studio 32gb",
    # MacBook Air
    "macbook air", "macbook air m4", "macbook air m3", "macbook air m2", "macbook air m1",
    "macbook air 24gb", "macbook air 32gb", "macbook air 64gb",
    # MacBook Pro
    "macbook pro", "macbook pro m4", "macbook pro m4 pro", "macbook pro m4 max",
    "macbook pro m3", "macbook pro m3 pro", "macbook pro m3 max",
    "macbook pro m2", "macbook pro m2 pro", "macbook pro m2 max",
    "macbook pro m1", "macbook pro m1 pro", "macbook pro m1 max",
    "macbook pro 24gb", "macbook pro 32gb", "macbook pro 64gb",
    # Generic Apple terms
    "apple macbook", "apple laptop", "apple computer", "apple desktop",
    "imac", "imac m3", "imac m4",
]

MIN_RAM = 24
MAX_AGE_DAYS = 28  # Limit to 4 weeks max
RAM_BONUS = {128: 25, 96: 22, 64: 20, 48: 15, 36: 12, 32: 10, 24: 5}  # 64GB+ gets highest weight

# MSRP ranges for legitimacy scoring (price ranges in INR)
MSRP = {
    # Mac Mini
    "mac mini m4": (46000, 60000), "mac mini m4 pro": (95000, 140000), "mac mini m4 max": (150000, 250000),
    "mac mini m2": (28000, 45000), "mac mini m2 pro": (65000, 100000), "mac mini m2 max": (100000, 160000),
    "mac mini m1": (20000, 35000), "mac mini m1 pro": (40000, 70000), "mac mini m1 max": (60000, 110000),
    # Mac Studio
    "mac studio m2": (150000, 300000), "mac studio m2 max": (200000, 400000),
    "mac studio m2 ultra": (300000, 600000), "mac studio m3": (180000, 350000),
    # MacBook Air
    "macbook air m4": (90000, 140000), "macbook air m3": (65000, 95000),
    "macbook air m2": (50000, 75000), "macbook air m1": (35000, 55000),
    # MacBook Pro
    "macbook pro m4": (120000, 250000), "macbook pro m4 pro": (180000, 350000), "macbook pro m4 max": (250000, 500000),
    "macbook pro m3": (90000, 180000), "macbook pro m3 pro": (140000, 280000), "macbook pro m3 max": (200000, 400000),
    "macbook pro m2": (65000, 120000), "macbook pro m2 pro": (100000, 200000), "macbook pro m2 max": (150000, 300000),
    "macbook pro m1": (45000, 80000), "macbook pro m1 pro": (70000, 140000), "macbook pro m1 max": (100000, 200000),
    # iMac
    "imac m3": (100000, 150000), "imac m4": (130000, 200000),
}

LEGIT_SCORE = {"fair_price": 100, "below_market": 80, "unverified": 50, "above_msrp": 30, "suspicious_low": 10}

# Composite score weights (must sum to 100)
SCORE_WEIGHTS = {
    "value": 25,       # Price vs MSRP
    "savings": 25,     # Real price - quoted
    "trust": 20,       # User trustworthiness
    "recency": 15,     # How recent the post is
    "description": 10, # Description quality/completeness
    "ram": 5,          # RAM bonus
}


def load_token():
    with open(TOKEN_PATH) as f:
        return json.load(f).get("access_token", "")

def mcp_call(method, params, token):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    req = urllib.request.Request(MCP_ENDPOINT, data=payload.encode(), headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {token}",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    for line in raw.split("\n"):
        if line.startswith("data: "):
            data = json.loads(line[6:])
            text = data.get("result", {}).get("content", [{}])[0].get("text", "{}")
            return json.loads(text)
    return {}

def firecrawl_scrape(url, token):
    result = mcp_call("tools/call", {
        "name": "COMPOSIO_MULTI_EXECUTE_TOOL",
        "arguments": {
            "tools": [{"tool_slug": "FIRECRAWL_SCRAPE", "arguments": {
                "url": url, "formats": ["markdown"],
            }}],
            "thought": "scrape OLX", "current_step": "firecrawl",
        }
    }, token)
    remote = result.get("data", {}).get("remote_file_info", {})
    fp = remote.get("file_path")
    if fp:
        return extract_remote(fp, token)
    results = result.get("data", {}).get("results", [])
    if results:
        md = results[0].get("response", {}).get("data", {}).get("data", {}).get("markdown", "")
        if md:
            return parse_olx_md(md)
    return []

def extract_remote(fp, token):
    script = (
        "import json\n"
        f"d = json.load(open('{fp}'))\n"
        "md = d['results'][0]['response']['data']['data']['markdown']\n"
        "s = md[7:-3].strip() if md.startswith('```json') else md.strip()\n"
        "j = json.loads(s)\n"
        "items = j.get('data', [])\n"
        "out = []\n"
        "for i in items:\n"
        "    t = i.get('title','')\n"
        "    p = i.get('price',{})\n"
        "    pv = p.get('value',{}).get('raw',0) if isinstance(p,dict) else 0\n"
        "    uid = i.get('id','')\n"
        "    u = f'https://www.olx.in/item/{uid}' if uid else ''\n"
        "    l = i.get('locations_resolved',{}).get('ADMIN_LEVEL_3_name','')\n"
        "    desc = i.get('description','')[:300]\n"
        "    cat = i.get('created_at','')\n"
        "    un = i.get('user_name','')\n"
        "    ut = i.get('user_type','')\n"
        "    uj = i.get('user_created_at','')\n"
        "    utag = i.get('user_tag','')\n"
        "    kyc = i.get('is_kyc_verified_user',False)\n"
        "    elite = i.get('elite_seller',False)\n"
        "    biz = i.get('is_business',False)\n"
        "    out.append({'title':t,'price':pv,'url':u,'loc':l,'desc':desc,'cat':cat,'uname':un,'utype':ut,'ujoin':uj,'utag':utag,'kyc':kyc,'elite':elite,'biz':biz})\n"
        "print(json.dumps(out))\n"
    )
    b64 = base64.b64encode(script.encode()).decode()
    result = mcp_call("tools/call", {
        "name": "COMPOSIO_REMOTE_BASH_TOOL",
        "arguments": {"command": f"echo {b64} | base64 -d | python3"}
    }, token)
    stdout = result.get("data", {}).get("stdout", "")
    if stdout:
        try: return json.loads(stdout.strip())
        except: pass
    return []

def parse_olx_md(md):
    s = md[7:-3].strip() if md.startswith("```json") else md.strip()
    try:
        j = json.loads(s)
        items = j.get("data", [])
        out = []
        for i in items:
            t = i.get("title", "")
            p = i.get("price", {})
            pv = p.get("value", {}).get("raw", 0) if isinstance(p, dict) else 0
            uid = i.get("id", "")
            u = f"https://www.olx.in/item/{uid}" if uid else ""
            l = i.get("locations_resolved", {}).get("ADMIN_LEVEL_3_name", "")
            desc = i.get("description", "")[:300]
            cat = i.get("created_at", "")
            un = i.get("user_name", "")
            ut = i.get("user_type", "")
            uj = i.get("user_created_at", "")
            utag = i.get("user_tag", "")
            kyc = i.get("is_kyc_verified_user", False)
            elite = i.get("elite_seller", False)
            biz = i.get("is_business", False)
            out.append({"title": t, "price": pv, "url": u, "loc": l, "desc": desc, "cat": cat, "uname": un, "utype": ut, "ujoin": uj, "utag": utag, "kyc": kyc, "elite": elite, "biz": biz})
        return out
    except:
        return []


def load_seen():
    if SEEN_FILE.exists():
        try: return json.loads(SEEN_FILE.read_text())
        except: return {}
    return {}

def save_seen(seen):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - 30 * 86400
    pruned = {k: v for k, v in seen.items() if v > cutoff}
    SEEN_FILE.write_text(json.dumps(pruned, indent=2))

def extract_ram_gb(text):
    t = text.lower()
    m = re.search(r'(\d+)\s*gb', t)
    if m:
        return int(m.group(1))
    return None

def identify_product(text):
    t = text.lower()
    
    # MacBook Pro first (more specific)
    if "macbook pro" in t:
        if "m4 max" in t: return "macbook pro m4 max"
        if "m4 pro" in t: return "macbook pro m4 pro"
        if "m4" in t or ("2024" in t or "2025" in t): return "macbook pro m4"
        if "m3 max" in t: return "macbook pro m3 max"
        if "m3 pro" in t: return "macbook pro m3 pro"
        if "m3" in t or "2023" in t: return "macbook pro m3"
        if "m2 max" in t: return "macbook pro m2 max"
        if "m2 pro" in t: return "macbook pro m2 pro"
        if "m2" in t or "2022" in t: return "macbook pro m2"
        if "m1 max" in t: return "macbook pro m1 max"
        if "m1 pro" in t: return "macbook pro m1 pro"
        if "m1" in t or "2020" in t or "2021" in t: return "macbook pro m1"
        return None
    
    # MacBook Air
    elif "macbook air" in t:
        if "m4" in t or "2024" in t or "2025" in t: return "macbook air m4"
        if "m3" in t or "2023" in t: return "macbook air m3"
        if "m2" in t or "2022" in t: return "macbook air m2"
        if "m1" in t or "2020" in t or "2021" in t: return "macbook air m1"
        return None
    
    # Mac Studio
    elif "mac studio" in t:
        if "m2 ultra" in t: return "mac studio m2 ultra"
        if "m2 max" in t: return "mac studio m2 max"
        if "m3" in t: return "mac studio m3"
        if "m2" in t: return "mac studio m2"
        return "mac studio m2"
    
    # Mac Mini
    elif "mac mini" in t or "mini mac" in t:
        if "m4 max" in t: return "mac mini m4 max"
        if "m4 pro" in t: return "mac mini m4 pro"
        elif "m4" in t: return "mac mini m4"
        if "m2 max" in t: return "mac mini m2 max"
        if "m2 pro" in t: return "mac mini m2 pro"
        elif "m2" in t: return "mac mini m2"
        if "m1 max" in t: return "mac mini m1 max"
        if "m1 pro" in t: return "mac mini m1 pro"
        elif "m1" in t: return "mac mini m1"
        return None
    
    # iMac
    elif "imac" in t:
        if "m4" in t or "2024" in t or "2025" in t: return "imac m4"
        if "m3" in t or "2023" in t: return "imac m3"
        return "imac m3"
    
    # Generic Apple computer/laptop
    elif "apple" in t and ("laptop" in t or "computer" in t or "desktop" in t or "mac" in t):
        if "m4" in t: return "macbook pro m4"
        if "m3" in t: return "macbook pro m3"
        if "m2" in t: return "macbook pro m2"
        if "m1" in t: return "macbook pro m1"
        return None
    
    return None

def value_score(price, ptype):
    if ptype not in MSRP: return 50
    low, high = MSRP[ptype]
    mid = (low + high) / 2
    return max(0, min(100, int((mid - price) / mid * 100 + 50)))

def real_price(ptype):
    """Return MSRP midpoint as real market price."""
    if ptype not in MSRP: return 0
    low, high = MSRP[ptype]
    return (low + high) // 2

def bargain_price(price, ptype):
    """Suggest a bargain price (10-15% below quoted, or near low MSRP)."""
    if ptype not in MSRP: return int(price * 0.85)
    low, high = MSRP[ptype]
    # Target: 10% below quoted, but not below 70% of low MSRP
    target = int(price * 0.90)
    floor = int(low * 0.70)
    return max(target, floor)

def description_score(desc):
    """Score description quality 0-100 based on completeness."""
    if not desc: return 0
    score = 0
    d = desc.lower()
    # Length bonus
    if len(desc) > 100: score += 20
    if len(desc) > 200: score += 10
    # Specific details
    if any(w in d for w in ["battery", "health", "cycle"]): score += 20
    if any(w in d for w in ["warranty", "apple care", "applecare"]): score += 15
    if any(w in d for w in ["condition", "mint", "excellent", "like new"]): score += 10
    if any(w in d for w in ["price", "fixed", "negotiable"]): score += 10
    if any(w in d for w in ["reason", "selling", "upgrade"]): score += 10
    if any(w in d for w in ["box", "invoice", "bill"]): score += 5
    # Negative signals
    if any(w in d for w in ["want to buy", "wtb", "looking for"]): score -= 30
    if any(w in d for w in ["damaged", "broken", "not working"]): score -= 20
    return max(0, min(100, score))

def recency_score(days_ago):
    """Score recency 0-100 (newer = higher)."""
    if days_ago <= 0: return 100
    if days_ago <= 1: return 95
    if days_ago <= 3: return 90
    if days_ago <= 7: return 80
    if days_ago <= 14: return 65
    if days_ago <= 21: return 50
    if days_ago <= 28: return 35
    return 20

def composite_score(price, ptype, ram, utrust, days_ago, desc):
    """Calculate normalized composite score 0-100."""
    # Value component (0-100)
    vs = value_score(price, ptype)
    
    # Savings component (0-100): % off real price
    rp = real_price(ptype)
    if rp > 0:
        savings_pct = max(0, (rp - price) / rp * 100)
        savings = min(100, int(savings_pct * 2))  # 50% off = 100 score
    else:
        savings = 50
    
    # Trust component (already 0-100)
    trust = utrust
    
    # Recency component (0-100)
    rec = recency_score(days_ago)
    
    # Description component (0-100)
    desc_s = description_score(desc)
    
    # RAM bonus component (0-100)
    ram_s = min(100, RAM_BONUS.get(ram, 0) * 5) if ram else 0
    
    # Weighted sum
    total = (
        vs * SCORE_WEIGHTS["value"] / 100 +
        savings * SCORE_WEIGHTS["savings"] / 100 +
        trust * SCORE_WEIGHTS["trust"] / 100 +
        rec * SCORE_WEIGHTS["recency"] / 100 +
        desc_s * SCORE_WEIGHTS["description"] / 100 +
        ram_s * SCORE_WEIGHTS["ram"] / 100
    )
    return round(total, 1)

def legitimacy(price, ptype):
    if ptype not in MSRP: return ["unverified"]
    low, high = MSRP[ptype]
    if price < low * 0.4: return ["suspicious_low"]
    if price < low * 0.7: return ["below_market"]
    if price <= high * 1.1: return ["fair_price"]
    return ["above_msrp"]

def parse_recency(created_at_str):
    if not created_at_str:
        return 999, "unknown"
    try:
        dt = datetime.fromisoformat(created_at_str)
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = now - dt
        days = delta.days
        if days == 0: return 0, "today"
        elif days == 1: return 1, "1d ago"
        elif days < 7: return days, f"{days}d ago"
        elif days < 30: return days, f"{days//7}w ago"
        elif days < 365: return days, f"{days//30}mo ago"
        else: return days, f"{days//365}y ago"
    except:
        return 999, "unknown"

def parse_user_join_date(ujoin_str):
    """Parse user join date and return (account_age_days, display_str)."""
    if not ujoin_str or ujoin_str == "N/A":
        return -1, "hidden"
    try:
        dt = datetime.fromisoformat(ujoin_str)
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = now - dt
        days = delta.days
        if days < 30: return days, f"{days}d"
        elif days < 365: return days, f"{days//30}mo"
        else: return days, f"{days//365}y"
    except:
        return -1, "hidden"

def user_trust_score(utype, ujoin_days, kyc, elite, biz, utag):
    """Calculate user trust score 0-100."""
    score = 50  # base
    if kyc: score += 20
    if elite: score += 15
    if biz: score += 10
    if ujoin_days > 365: score += 10  # 1+ year account
    elif ujoin_days > 180: score += 5  # 6+ months
    if utag and "disapproved" in utag.lower(): score -= 20
    if utype == "Business": score += 10
    return max(0, min(100, score))


def main():
    token = load_token()
    seen = load_seen()
    all_deals = []

    for query in QUERIES:
        url = OLX_API + "&query=" + query.replace(" ", "+")
        print(f"[INFO] Scraping: {query}", file=sys.stderr)
        try:
            items = firecrawl_scrape(url, token)
            print(f"[INFO] Got {len(items)} items for '{query}'", file=sys.stderr)
            for item in items:
                title = item.get("title", "")
                price = item.get("price", 0)
                olx_url = item.get("url", "")
                loc = item.get("loc", "")
                desc = item.get("desc", "")
                created = item.get("cat", "")
                uname = item.get("uname", "")
                utype = item.get("utype", "")
                ujoin = item.get("ujoin", "")
                utag = item.get("utag", "")
                kyc = item.get("kyc", False)
                elite = item.get("elite", False)
                biz = item.get("biz", False)

                if "hyderabad" not in loc.lower() and loc:
                    continue

                ptype = identify_product(title)
                if not ptype or price < 10000:
                    continue

                ram = extract_ram_gb(title + " " + desc)
                if ram is not None and ram < MIN_RAM:
                    continue

                deal_id = f"{olx_url}:{price}"
                if deal_id in seen:
                    continue

                legs = legitimacy(price, ptype)
                leg_score = min(LEGIT_SCORE.get(l, 0) for l in legs)
                days_ago, recency = parse_recency(created)
                
                # Skip deals older than 4 weeks
                if days_ago > MAX_AGE_DAYS:
                    continue
                
                ujoin_days, ujoin_str = parse_user_join_date(ujoin)
                utrust = user_trust_score(utype, ujoin_days, kyc, elite, biz, utag)
                
                # RAM bonus for 32GB+
                ram_bonus = RAM_BONUS.get(ram, 0) if ram else 0
                base_score = value_score(price, ptype)
                total_score = min(100, base_score + ram_bonus + (utrust // 5))
                
                # New columns
                rp = real_price(ptype)
                bp = bargain_price(price, ptype)
                cs = composite_score(price, ptype, ram, utrust, days_ago, desc)

                all_deals.append({
                    "title": title[:80],
                    "price": price,
                    "price_fmt": f"Rs.{int(price):,}",
                    "real_price": rp,
                    "real_price_fmt": f"Rs.{rp:,}" if rp else "—",
                    "bargain_price": bp,
                    "bargain_price_fmt": f"Rs.{bp:,}",
                    "url": olx_url,
                    "product_type": ptype,
                    "ram_gb": ram,
                    "score": cs,
                    "legitimacy": legs,
                    "legit_score": leg_score,
                    "desc": desc[:200].replace("\n", " ").replace("\r", ""),
                    "days_ago": days_ago,
                    "recency": recency,
                    "uname": uname[:30],
                    "utype": utype,
                    "ujoin": ujoin_str,
                    "utrust": utrust,
                    "kyc": kyc,
                    "elite": elite,
                })
                seen[deal_id] = time.time()
            time.sleep(2)
        except Exception as e:
            print(f"[WARN] '{query}' failed: {e}", file=sys.stderr)

    seen_urls = set()
    unique = []
    for d in all_deals:
        if d["url"] not in seen_urls:
            seen_urls.add(d["url"])
            unique.append(d)

    # Sort: composite score DESC (best deals first), then recency ASC, then price ASC
    all_deals = sorted(unique, key=lambda d: (-d["score"], d["days_ago"], d["price"]))
    save_seen(seen)

    if not all_deals:
        print("[SILENT] No new OLX Hyderabad Mac deals found.")
        return

    legit_count = sum(1 for d in all_deals if d["legit_score"] >= 80)
    warn_count = sum(1 for d in all_deals if d["legit_score"] <= 30)

    print(f"**OLX Hyderabad Mac Deals: {len(all_deals)}** ({legit_count} legit, {warn_count} suspicious)\n")

    for d in all_deals[:25]:
        if d["legit_score"] >= 100: emoji = "FAIR"
        elif d["legit_score"] >= 80: emoji = "GOOD"
        elif d["legit_score"] >= 50: emoji = "?"
        elif d["legit_score"] >= 30: emoji = "HIGH"
        else: emoji = "SUS"

        ram_str = f" ({d['ram_gb']}GB)" if d["ram_gb"] else ""
        print(f"[{emoji}] **{d['product_type'].upper()}{ram_str}** - {d['price_fmt']} [{d['recency']}]")
        print(f"  {d['title']}")
        print(f"  Desc: {d['desc'][:100]}...")
        print(f"  Score: {d['score']}/100 | Link: {d['url']}\n")

    # Google Doc
    try:
        def stars(score):
            """Return star rating based on value score."""
            if score >= 90: return "⭐⭐⭐"
            elif score >= 70: return "⭐⭐"
            elif score >= 50: return "⭐"
            else: return ""

        def leg_emoji(leg_score):
            """Return emoji for legitimacy."""
            if leg_score >= 100: return "✅"  # Fair price
            elif leg_score >= 80: return "🟢"  # Below market
            elif leg_score >= 50: return "🟡"  # Unverified
            elif leg_score >= 30: return "🟠"  # Above MSRP
            else: return "🔴"  # Suspicious

        def recency_badge(days):
            """Return recency badge."""
            if days == 0: return "🆕 TODAY"
            elif days <= 1: return "🟢 1d"
            elif days <= 7: return f"🟡 {days}d"
            elif days <= 30: return "🟠 {w}w".format(w=days//7)
            else: return "🔴 {m}mo".format(m=days//30)

        # Summary header
        top3 = all_deals[:3]
        top_items = []
        for d in top3:
            ram_str = f" {d['ram_gb']}GB" if d["ram_gb"] else ""
            savings = d["real_price"] - d["price"] if d["real_price"] > 0 else 0
            savings_str = f" (save Rs.{savings:,})" if savings > 0 else ""
            top_items.append(f"• **{d['product_type'].upper()}{ram_str}** — {d['price_fmt']}{savings_str} [Score: {d['score']}] [{d['recency']}]")

        summary = f"""# 🍎 OLX Hyderabad Mac Deals — {datetime.now().strftime('%d %B %Y')}

---

## 📊 Quick Stats
| Metric | Value |
|--------|-------|
| **Total Deals** | {len(all_deals)} |
| **✅ Legit (Fair/Below)** | {legit_count} |
| **🔴 Suspicious** | {warn_count} |

---

## 🏆 Top 3 Deals
{chr(10).join(top_items)}

---

## 📋 All Deals (sorted by composite score)

| # | Score | Status | Recency | Product | RAM | Price | Real Price | Bargain | Seller | Since | Trust | Description | Link |
|---|-------|--------|---------|---------|-----|-------|------------|---------|---------|-------|-------|-------------|------|"""

        for i, d in enumerate(all_deals[:50], 1):
            leg = leg_emoji(d["legit_score"])
            rec = recency_badge(d["days_ago"])
            # Score display with color indicator
            sc = d["score"]
            if sc >= 70: score_badge = f"🟢 {sc}"
            elif sc >= 50: score_badge = f"🟡 {sc}"
            else: score_badge = f"🔴 {sc}"
            ram_str = f"{d['ram_gb']}GB" if d["ram_gb"] else "?"
            link_cell = f"[🔗]({d['url']})" if d["url"] else "N/A"
            desc_short = d["desc"][:40].replace("|", "/").replace("\n", " ")
            seller = d["uname"][:20] if d["uname"] else "?"
            since = d["ujoin"] if d["ujoin"] and d["ujoin"] != "hidden" else "—"
            trust = f"{d['utrust']}/100"
            kyc_badge = " ✓" if d.get("kyc") else ""
            elite_badge = " ⭐" if d.get("elite") else ""
            summary += f"\n| {i} | {score_badge} | {leg} | {rec} | {d['product_type']} | {ram_str} | {d['price_fmt']} | {d['real_price_fmt']} | {d['bargain_price_fmt']} | {seller}{kyc_badge}{elite_badge} | {since} | {trust} | {desc_short} | {link_cell} |"

        summary += """

---

## 🔍 Legend
- **✅** = Fair price | **🟢** = Below market | **🟡** = Unverified | **🟠** = Above MSRP | **🔴** = Suspicious
- **🆕** = Today | **🟢** = 1d | **🟡** = This week | **🟠** = This month | **🔴** = Older
- **✓** = KYC verified | **⭐** = Elite seller
- **Score** = Composite score (0-100): Value + Savings + Trust + Recency + Description + RAM
- **Real Price** = MSRP market value | **Bargain** = Suggested negotiation target
- **Trust** = Seller reliability (account age + verification + status)
- **Since** = Account age (d=days, mo=months, y=years)
- **—** = Data not available from OLX

---
*Generated by Hermes Agent — OLX Hyderabad Mac Scanner*
"""
        title = f"OLX Hyderabad Mac Deals - {datetime.now().strftime('%Y-%m-%d')}"
        result = mcp_call("tools/call", {
            "name": "COMPOSIO_MULTI_EXECUTE_TOOL",
            "arguments": {
                "tools": [{"tool_slug": "GOOGLEDOCS_CREATE_DOCUMENT_MARKDOWN", "arguments": {
                    "title": title, "markdown_text": summary,
                }}],
                "thought": "create doc", "current_step": "gdoc",
            }
        }, token)
        text = json.dumps(result)
        doc_match = re.search(r'"documentId"\s*:\s*"([^"]+)"', text)
        if doc_match:
            doc_id = doc_match.group(1)
            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
            print(f"\nGoogle Doc: {doc_url}")

            mcp_call("tools/call", {
                "name": "COMPOSIO_MULTI_EXECUTE_TOOL",
                "arguments": {
                    "tools": [{"tool_slug": "GOOGLEDRIVE_CREATE_PERMISSION", "arguments": {
                        "file_id": doc_id, "type": "user", "role": "reader",
                        "email_address": USER_EMAIL,
                    }}],
                    "thought": "share", "current_step": "share",
                }
            }, token)

            top3 = all_deals[:3]
            top_html = "".join(
                f"<li><b>{d['product_type']}</b> - {d['price_fmt']} [{d['recency']}] <a href='{d['url']}'>OLX Link</a></li>"
                for d in top3
            )
            mcp_call("tools/call", {
                "name": "COMPOSIO_MULTI_EXECUTE_TOOL",
                "arguments": {
                    "tools": [{"tool_slug": "GMAIL_SEND_EMAIL", "arguments": {
                        "to": USER_EMAIL,
                        "subject": f"OLX Hyderabad Mac Deals - {legit_count} legit / {len(all_deals)} total",
                        "is_html": True,
                        "body": f"<h2>OLX Hyderabad Mac Deals</h2><p>Found <b>{len(all_deals)}</b> deals ({legit_count} legit).</p><h3>Top Deals (newest first):</h3><ul>{top_html}</ul><p><a href='{doc_url}'>View Full Doc</a></p><p>- Hermes Agent</p>",
                    }}],
                    "thought": "email", "current_step": "email",
                }
            }, token)
            print(f"Email sent to {USER_EMAIL}")
    except Exception as e:
        print(f"\n[WARN] Google actions failed: {e}", file=sys.stderr)

    print("\n---JSON_SUMMARY---")
    print(json.dumps({
        "total": len(all_deals),
        "legit": legit_count,
        "top": [{"title": d["title"], "price": d["price_fmt"], "recency": d["recency"], "legitimacy": d["legitimacy"][0], "url": d["url"]} for d in all_deals[:10]],
    }, indent=2))

if __name__ == "__main__":
    main()
