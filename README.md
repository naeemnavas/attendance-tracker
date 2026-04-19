# 📊 Attendance Tracker

An unofficial attendance checker for SH College students. Enter your student portal credentials and instantly see your subject-wise attendance, how many classes you can skip, or how many you need to attend to hit your target percentage.

> ⚠️ **Unofficial tool** — not affiliated with SH College or its ERP system. Use at your own risk.

---

## Features

- 🔐 Logs into the college portal on your behalf using a headless browser (Playwright)
- 📋 Fetches and parses your subject-wise attendance table
- 🧮 Calculates current %, classes needed, and classes you can safely skip
- 📥 Download your attendance summary as a PNG image
- 🔒 Credentials are **never stored** — used only for the live request, then discarded

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python · FastAPI · Uvicorn |
| Scraping | Playwright (headless Chromium) |
| Parsing | BeautifulSoup4 |
| Frontend | Vanilla HTML / CSS / JS |
| Hosting | Render (free tier) |

---

## Local Development

### Prerequisites
- Python 3.11+
- pip

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/naeemnavas/attendance-tracker.git
cd attendance-tracker

# 2. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browser
python -m playwright install chromium

# 5. Run the dev server
uvicorn main:app --reload --port 8002
```

Open [http://localhost:8002](http://localhost:8002) in your browser.

---

## Deployment (Render)

A `render.yaml` is included. To deploy:

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → **New Web Service**
3. Connect your GitHub repo
4. Render auto-detects `render.yaml` and configures everything

Build command installs dependencies and Playwright's Chromium browser automatically.

---

## Project Structure

```
attendance-tracker/
├── main.py            # FastAPI app — scraping, parsing, API endpoints
├── render.yaml        # Render deployment config
├── requirements.txt   # Python dependencies
├── static/
│   └── index.html     # Single-page frontend
└── README.md
```

---

## Privacy

- Your username and password are sent **directly to the college portal** over HTTPS
- They are held in server memory only for the duration of the scrape, then discarded
- Nothing is written to disk or any database
- The server stores no session, no logs, no user data
