# ClearPresence Digital

Marketing website + lead generation tools for a local business review management and Google Business Profile service.

- **Live site**: clearpresencedigital.com
- **Hosting**: GitHub Pages (auto-deploys on push to `main`)

---

## Lead Scraper

Scrapes Google Maps listings, scores their online presence quality, and stores everything in a local SQLite CRM database. Businesses with poor online presence (few reviews, no photos, no owner responses) are flagged as high-priority prospects.

### Prerequisites

- Python 3.10+
- Google Chrome or Chromium browser installed
- ChromeDriver (matching your Chrome version)

On Ubuntu/Debian:
```bash
sudo apt install -y chromium-browser chromium-chromedriver
```

### Setup

```bash
cd lead-scraper

# Create virtual environment (one time)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install selenium pandas openpyxl
```

### Usage

```bash
cd lead-scraper
source venv/bin/activate

# Basic run — scrape up to 20 listings, output only high-priority leads (score >= 5)
python3 scraper.py "plumbers east brunswick nj"

# Limit to 10 listings
python3 scraper.py "plumbers east brunswick nj" --max 10

# Show all leads with scores (no filtering)
python3 scraper.py "plumbers east brunswick nj" --all

# Lower the score threshold to catch more leads
python3 scraper.py "plumbers east brunswick nj" --min-score 3
```

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `query` | *(required)* | Google Maps search query |
| `--max N` | 20 | Maximum number of listings to scrape |
| `--min-score N` | 5 | Minimum lead score for output (higher = worse online presence) |
| `--all` | off | Output all listings regardless of score |

### How Scoring Works

Each listing is scored on quality signals. Higher score = worse online presence = better prospect for our services.

| Signal | Points |
|--------|--------|
| < 10 reviews | +3 |
| No owner responses to reviews | +2 |
| < 5 photos | +2 |
| Rating below 4.0 | +2 |
| No recent reviews (6+ months) | +2 |
| No description | +1 |
| No services listed | +1 |
| No website | +1 |
| **Maximum possible** | **~14** |

Score >= 5 = High Priority Lead (default threshold).

### Output

Each run produces three things:

1. **JSON file** — `lead-scraper/output/<query>_<timestamp>.json`
2. **Excel file** — `lead-scraper/output/<query>_<timestamp>.xlsx`
3. **SQLite database** — `lead-scraper/leads.db` (persistent across runs)

Console output shows scored leads sorted best-prospect-first:
```
  [SCORE  8] Joe's Plumbing                     | (732) 555-1234   | joesplumbing.com
           → <10 reviews, no owner responses, <5 photos, no description
```

### SQLite CRM Database

The database (`leads.db`) is the persistent source of truth. It stores:

- **Scraped data**: name, address, phone, website, rating, review count, category, maps link, photo URL
- **Quality signals**: photo count, has description, has services, owner responds, newest review date, has hours
- **Lead scoring**: score and reasons
- **CRM tracking**: contact status, last contacted date, notes
- **Metadata**: search query, scraped/updated timestamps

**Deduplication**: Uses `maps_link` as a unique key. Re-scraping the same business updates scraped fields but preserves your CRM fields (contact_status, last_contacted, notes).

You can query the database directly:
```bash
# View all high-priority leads
sqlite3 lead-scraper/leads.db "SELECT name, phone, lead_score, score_reasons FROM leads WHERE lead_score >= 5 ORDER BY lead_score DESC"

# Check CRM status
sqlite3 lead-scraper/leads.db "SELECT name, contact_status, last_contacted, notes FROM leads WHERE contact_status != 'new'"

# Update a lead's status
sqlite3 lead-scraper/leads.db "UPDATE leads SET contact_status='contacted', last_contacted='2026-02-05', notes='Left voicemail' WHERE name LIKE '%Joe%'"
```

### Project Structure

```
lead-scraper/
  scraper.py      # Main scraper script
  leads.db        # SQLite CRM database (auto-created on first run)
  output/         # JSON + Excel exports per run
  venv/           # Python virtual environment
```
