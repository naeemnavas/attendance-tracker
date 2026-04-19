import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import math

from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from pydantic import BaseModel

app = FastAPI(title="SH College Attendance Tracker")

BASE_URL        = "https://shcollege.online"
LOGIN_PAGE_URL  = f"{BASE_URL}/studentlogin"
ATTENDANCE_URL  = f"{BASE_URL}/Student/StudentAttendanceProfile/Create"
LOGOUT_URL      = f"{BASE_URL}/StudentLogin/Logout"


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class AttendanceRequest(BaseModel):
    username: str
    password: str
    target_percent: float = 75.0


# ---------------------------------------------------------------------------
# Calculation logic
# ---------------------------------------------------------------------------

def calculate_stats(conducted: int, effective_present: int, target_pct: float) -> dict:
    """
    effective_present = Present + Co-Curricular
    Formula:
      - classes needed  = ceil((T*C - 100*P) / (100 - T))
      - classes can skip = floor((100*P - T*C) / T)
    """
    if conducted == 0:
        return {"current_pct": 0.0, "status": "no_data",
                "classes_needed": 0, "classes_can_skip": 0}

    current_pct = round((effective_present / conducted) * 100, 2)

    if current_pct < target_pct:
        num = target_pct * conducted - 100 * effective_present
        den = 100 - target_pct
        needed = math.ceil(num / den) if den > 0 else 0
        return {"current_pct": current_pct, "status": "below",
                "classes_needed": max(0, needed), "classes_can_skip": 0}
    else:
        num = 100 * effective_present - target_pct * conducted
        den = target_pct
        skippable = math.floor(num / den) if den > 0 else 0
        return {"current_pct": current_pct,
                "status": "above" if current_pct > target_pct else "exact",
                "classes_needed": 0, "classes_can_skip": max(0, skippable)}


# ---------------------------------------------------------------------------
# Parse the rendered table HTML
# ---------------------------------------------------------------------------

def parse_attendance(html: str, target_pct: float):
    soup = BeautifulSoup(html, "html.parser")
    subjects = []
    total_data = None

    for row in soup.find_all("tr"):
        cells = row.find_all("td")

        # Data row: 8 cells, first cell is a digit
        if len(cells) == 8:
            sl_no = cells[0].get_text(strip=True)
            if sl_no.isdigit():
                try:
                    subject_name  = cells[1].get_text(strip=True)
                    att_type      = cells[2].get_text(strip=True)
                    conducted     = int(cells[3].get_text(strip=True))
                    present       = int(cells[4].get_text(strip=True))
                    absent        = int(cells[5].get_text(strip=True))
                    cocurricular  = int(cells[6].get_text(strip=True))
                    effective     = present + cocurricular
                    stats = calculate_stats(conducted, effective, target_pct)
                    subjects.append({
                        "sl_no": sl_no, "subject": subject_name,
                        "type": att_type, "conducted": conducted,
                        "present": present, "absent": absent,
                        "cocurricular": cocurricular, **stats,
                    })
                except (ValueError, IndexError):
                    continue

        # Total row
        elif len(cells) >= 6 and cells[0].get_text(strip=True) == "Total":
            try:
                conducted    = int(cells[1].get_text(strip=True))
                present      = int(cells[2].get_text(strip=True))
                absent       = int(cells[3].get_text(strip=True))
                cocurricular = int(cells[4].get_text(strip=True))
                effective    = present + cocurricular
                stats = calculate_stats(conducted, effective, target_pct)
                total_data = {"conducted": conducted, "present": present,
                              "absent": absent, "cocurricular": cocurricular, **stats}
            except (ValueError, IndexError):
                pass

    return (subjects or None), total_data


# ---------------------------------------------------------------------------
# Playwright scraper — runs a real headless browser so AJAX executes
# ---------------------------------------------------------------------------

_executor = ThreadPoolExecutor(max_workers=4)

def _scrape_attendance_sync(username: str, password: str, target_pct: float):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()

        try:
            # ── 1. Login ──────────────────────────────────────────────────
            print(f"[1] Navigating to login page...")
            page.goto(LOGIN_PAGE_URL, wait_until="domcontentloaded", timeout=30000)

            page.fill("#UserName", username.strip())
            page.fill("#Password", password)
            print(f"[2] Submitting login for: {username.strip()}")
            page.click("button[type=submit]")

            # Wait for redirect away from login page
            try:
                page.wait_for_url("**/Student/**", timeout=15000)
                print(f"[2] Login SUCCESS — now at: {page.url}")
            except PlaywrightTimeout:
                # Check if we're still on login (wrong credentials)
                if "login" in page.url.lower():
                    error_el = page.query_selector(".validation-summary-errors, .text-danger, .alert")
                    msg = error_el.inner_text() if error_el else "Invalid username or password."
                    return None, None, f"Login failed: {msg.strip()}"

            # ── 2. Navigate to attendance page ────────────────────────────
            print(f"[3] Navigating to attendance page...")
            page.goto(ATTENDANCE_URL, wait_until="domcontentloaded", timeout=30000)

            # ── 3. Wait for AJAX to populate the table ────────────────────
            print("[3] Waiting for attendance table to load via AJAX...")
            page.wait_for_selector(
                "#tblsubjectwiseattendence tr",
                state="attached",
                timeout=20000
            )
            print("[3] Table loaded!")

            # ── 4. Grab the rendered table HTML ───────────────────────────
            table_html = page.inner_html("#tblsubjectwiseattendence")
            print(f"[4] Got table HTML ({len(table_html)} chars)")

            subjects, total = parse_attendance(table_html, target_pct)
            print(f"[4] Parsed: {len(subjects) if subjects else 0} subjects, total={total is not None}")

            # ── 5. Logout ─────────────────────────────────────────────────
            try:
                page.goto(LOGOUT_URL, timeout=10000)
                # Confirm logout by checking we landed back on the login page
                if "login" in page.url.lower() or "studentlogin" in page.url.lower():
                    print(f"[5] Logout confirmed — redirected to: {page.url}")
                else:
                    print(f"[5] Logout may have failed — ended up at: {page.url}")
            except Exception as ex:
                print(f"[5] Logout failed: {ex}")  # Browser closes anyway

            return subjects, total, None

        except PlaywrightTimeout:
            return None, None, "The college portal timed out. Please try again."
        except Exception as exc:
            print(f"[ERROR] {exc}")
            return None, None, f"Unexpected error: {exc}"
        finally:
            browser.close()


async def scrape_attendance(username: str, password: str, target_pct: float):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor, _scrape_attendance_sync, username, password, target_pct
    )


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------

@app.post("/api/attendance")
async def get_attendance(req: AttendanceRequest):
    if not req.username.strip() or not req.password.strip():
        raise HTTPException(status_code=400, detail="Username and password are required.")
    if not (1 <= req.target_percent <= 99):
        raise HTTPException(status_code=400, detail="Target % must be between 1 and 99.")

    subjects, total, error = await scrape_attendance(
        req.username, req.password, req.target_percent
    )

    if error:
        status = 401 if "Login failed" in error else 500
        return JSONResponse(status_code=status, content={"error": error})

    if not subjects:
        return JSONResponse(status_code=404, content={
            "error": "No attendance records found. You may not have data for this semester yet."
        })

    return {
        "success": True,
        "student_id": req.username.upper(),
        "target_percent": req.target_percent,
        "subjects": subjects,
        "total": total,
    }


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", encoding="utf-8") as fh:
        return fh.read()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def devtools_stub():
    return JSONResponse(status_code=200, content={})
