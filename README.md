# 🍎 OLX Deal Hunter

Automated OLX India deal scanner for Mac/Mini/Studio/MacBook with legitimacy scoring, user trust analysis, and Google Docs reporting.

## Features

- **Real-time scraping** via Firecrawl through Composio MCP
- **Legitimacy scoring** based on MSRP comparison
- **User trust analysis** (KYC, elite seller, account age)
- **RAM bonus** for 32GB+ configurations
- **4-week deal freshness** filter
- **Google Docs** auto-generated reports with emoji indicators
- **Email notifications** with top 3 deals
- **Deduplication** via seen-deals tracking

## Scoring System

### Legitimacy (0-100)
| Score | Status | Meaning |
|-------|--------|---------|
| ✅ 100 | Fair Price | Within market range |
| 🟢 80 | Below Market | Good deal! |
| 🟡 50 | Unverified | No MSRP data |
| 🟠 30 | Above MSRP | Overpriced |
| 🔴 10 | Suspicious | Likely scam |

### Value Score
- Base: Price vs MSRP comparison
- RAM Bonus: +5 to +15 for 24GB-64GB
- Trust Bonus: +0 to +10 based on seller trust

### User Trust (0-100)
| Factor | Impact |
|--------|--------|
| KYC Verified | +20 |
| Elite Seller | +15 |
| Business Account | +10 |
| 1+ Year Account | +10 |
| 6+ Month Account | +5 |
| Disapproved Tag | -20 |

## Setup

### Prerequisites
- Python 3.10+
- Composio MCP access with Firecrawl enabled
- Composio token at `~/.hermes/mcp-tokens/composio.json`

### Environment Variables
```bash
# Optional: Override default paths
export COMPOSIO_TOKEN_PATH="~/.hermes/mcp-tokens/composio.json"
export USER_EMAIL="your-email@gmail.com"
```

### Running Manually
```bash
python3 olx-deal-hunter.py
```

### Cron Job (Hermes Agent)
```bash
hermes cron create --schedule "0 9 * * *" --script olx-deal-hunter.py
```

## Configuration

Edit the script to customize:

```python
# Location (Hyderabad = 4058526)
OLX_API = "https://www.olx.in/api/relevance/v4/search?location=4058526"

# Minimum RAM filter (GB)
MIN_RAM = 24

# Maximum deal age (days)
MAX_AGE_DAYS = 28

# RAM bonus scoring
RAM_BONUS = {64: 15, 48: 12, 36: 10, 32: 8, 24: 5}

# MSRP ranges (low, high) in INR
MSRP = {
    "mac mini m4": (46000, 60000),
    "macbook pro m4": (120000, 250000),
    # ... add more products
}
```

## Output

### Google Docs
- Auto-generated daily report
- Shared with configured email
- Emoji-based visual indicators
- Sorted by newest + most legitimate

### Email
- Top 3 deals highlighted
- Link to full Google Doc

## Data Flow

```
OLX API → Firecrawl → Parse → Score → Filter → Google Docs → Email
                                ↓
                         Seen Deals DB
```

## File Structure

```
olx-deal-hunter/
├── olx-deal-hunter.py      # Main script
├── olx-mac-deals-seen.json  # Dedup database (auto-created)
├── README.md                # This file
└── AGENTS.md                # AI agent instructions
```

## Troubleshooting

### "No new deals found"
- Check `olx-mac-deals-seen.json` - may need to clear old entries
- Verify Composio token is valid
- Check Firecrawl API status

### Google Doc not created
- Verify Google Docs MCP is enabled
- Check Composio permissions

### Low deal count
- Check MIN_RAM filter (set to 0 for all deals)
- Verify location ID is correct
- Check MAX_AGE_DAYS setting

## License

MIT
