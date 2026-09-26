# FastestScore Football Live Bot ⚽🤖

An automated, high-concurrency Python bot that tracks live football match events across 30+ global leagues and instantly publishes real-time updates (lineups, kick-offs, goals, half-time, and full-time) directly to a Facebook Page via the Facebook Graph API. 

Designed for continuous deployment on cloud platforms (like Render or Heroku), the application wraps the background scraping engine in a Flask web server to maintain cloud health checks while handling intensive network polling via threaded execution.

## Core Features
* **Multi-League Concurrency:** Utilizes Python's `ThreadPoolExecutor` (20 workers) to simultaneously track over 30 major competitions without I/O blocking.
* **Insta-Goal Detection & Ninja Edits:** Detects goals within seconds of them hitting the ESPN API. If assist data is delayed, a background daemon (`_hunt_missing_goal`) continuously monitors the event and silently edits the Facebook post to inject the assist data once available.
* **Smart State Management:** Uses a local SQLite database (`espn_bot_multi.db`) with `RLock` threading protection to cache match states, track posted events, and prevent duplicate API posts during server restarts.
* **TLS Fingerprint Spoofing:** Uses `curl_cffi` to impersonate a Chrome browser network request, effectively bypassing automated bot-blocking mechanisms.
* **VIP Team Targeting:** Custom filtering prioritizes high-engagement teams (e.g., Al Nassr in the Saudi Pro League, Inter Miami in the MLS).
* **Automated Morning Digest:** Compiles and posts a daily match schedule at 7:00 AM (WAT) for all tracked leagues.

## Tech Stack
* **Language:** Python 3
* **Web Framework:** Flask (Lightweight health-check server)
* **Concurrency:** `threading`, `concurrent.futures.ThreadPoolExecutor`
* **Database:** SQLite3
* **Network & APIs:** `curl_cffi` (Requests), Facebook Graph API v19.0, ESPN Hidden APIs

## Repository Structure
* `All_league_espn.py`: The main application script containing the Flask server and the `MultiLeagueBot` class.
* `requirements.txt`: Contains project dependencies (`flask`, `curl_cffi`).
* `.gitignore`: Excludes local databases, Python caches, and environment variables from version control.

## Local Setup & Deployment

### 1. Environment Variables
The bot requires a Facebook Page Access Token to authenticate posts. You must set this in your environment before running the script.
```bash
export FB_TOKEN="your_facebook_page_access_token_here"
```

### 2. Installation
Clone the repository and install the required dependencies:
```bash
pip install -r requirements.txt
```

### 3. Running the Bot
Execute the main script. The Flask server will start on port 5000 (or the port defined by your hosting provider), while the scraping bot initializes in a background daemon thread:
```bash
python All_league_espn.py
```

## Engineering Architecture Highlights
* **Thread-Safe Database Operations:** Because multiple threads evaluate match states simultaneously, all SQLite read/write operations are wrapped in `threading.RLock()` to prevent database locking errors and corruption.
* **Cloud-Ready Web Server Integration:** Cloud providers require web services to bind to a designated `$PORT` within 60 seconds, or the instance is killed. This script safely isolates the infinite `while True` scraping loop in a daemon thread (`run_bot_in_background`), allowing the Flask `app.run` to bind successfully to `0.0.0.0:PORT` and keep the server alive.
* **Fault Tolerance:** API timeouts, JSON parsing errors, and network drops are handled gracefully inside isolated `try/except` blocks within the thread pool, ensuring that a crash in one league's tracking doesn't bring down the entire application.
