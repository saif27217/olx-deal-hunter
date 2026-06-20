# AGENTS.md - OLX Deal Hunter

## Project Overview
Automated OLX India deal scanner for Apple Mac products with legitimacy scoring, user trust analysis, and automated reporting.

## Agent Capabilities

### This agent can:
- Scrape OLX India via Firecrawl through Composio MCP
- Score deals based on price legitimacy
- Analyze seller trustworthiness
- Generate Google Docs reports
- Send email notifications
- Track seen deals to avoid duplicates

### This agent cannot:
- Access OLX directly (blocked from VPS)
- Make purchases or transactions
- Verify deal authenticity beyond scoring
- Access user personal information

## Code Structure

### Main Script: `olx-deal-hunter.py`

**Key Functions:**
- `firecrawl_scrape(url, token)` - Scrapes OLX API via Firecrawl
- `extract_remote(fp, token)` - Extracts data from remote sandbox files
- `parse_olx_md(md)` - Parses OLX JSON response
- `identify_product(text)` - Identifies Mac product type
- `value_score(price, ptype)` - Calculates value score (0-100)
- `legitimacy(price, ptype)` - Determines legitimacy category
- `user_trust_score(...)` - Calculates seller trust (0-100)
- `parse_recency(created_at)` - Parses ad creation date
- `main()` - Main execution flow

**Data Flow:**
```
OLX API → Firecrawl → Parse → Score → Filter → Google Docs → Email
                                ↓
                         Seen Deals DB (JSON)
```

## Configuration Points

### Location
```python
OLX_API = "https://www.olx.in/api/relevance/v4/search?location=4058526"
# Hyderabad = 4058526
# Delhi = 4058763
# Bangalore = 4058404
```

### Filters
```python
MIN_RAM = 24        # Minimum RAM in GB
MAX_AGE_DAYS = 28   # Maximum deal age in days
```

### Scoring
```python
RAM_BONUS = {64: 15, 48: 12, 36: 10, 32: 8, 24: 5}
LEGIT_SCORE = {"fair_price": 100, "below_market": 80, "unverified": 50, "above_msrp": 30, "suspicious_low": 10}
```

### MSRP Ranges (INR)
```python
MSRP = {
    "mac mini m4": (46000, 60000),
    "macbook pro m4": (120000, 250000),
    # Add more products as needed
}
```

## Dependencies

### Required
- Python 3.10+
- Composio MCP access
- Firecrawl enabled in Composio

### Optional
- Google Docs MCP (for doc generation)
- Gmail MCP (for email notifications)

## Error Handling

### Common Errors
1. **Firecrawl timeout** - Retry after 2 seconds
2. **Remote file extraction** - Uses base64 encoding to avoid escaping issues
3. **Google Doc creation** - Falls back to console output

### Logging
- `[INFO]` - Normal operation
- `[WARN]` - Non-fatal errors
- `[SILENT]` - No new deals found (cron-friendly)

## Testing

### Manual Run
```bash
python3 olx-deal-hunter.py
```

### Check Output
- Console: Deal summary with emojis
- Google Doc: Full report with all columns
- Email: Top 3 deals

### Verify Deduplication
```bash
cat olx-mac-deals-seen.json | python3 -m json.tool
```

## Maintenance

### Clear Seen Deals
```bash
rm olx-mac-deals-seen.json
```

### Update MSRP Ranges
Edit `MSRP` dictionary in script based on current market prices.

### Add New Products
1. Add to `QUERIES` list
2. Add to `MSRP` dictionary
3. Add to `identify_product()` function

## Security Notes

- Composio token stored at `~/.hermes/mcp-tokens/composio.json`
- No sensitive data in repo
- Seen deals DB contains only deal IDs and timestamps

## Cron Job

### Hermes Agent
```bash
hermes cron create \
  --name "olx-deal-hunter" \
  --schedule "0 9 * * *" \
  --script ~/olx-deal-hunter/olx-deal-hunter.py
```

### Standard Cron
```bash
0 9 * * * /usr/bin/python3 /home/sak/olx-deal-hunter/olx-deal-hunter.py
```
