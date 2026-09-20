import os
import time
import re
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests
from flask import Flask

#========================================
# POST BRANDING BUILDER (MODERN PRO)
#========================================
class PostBuilder:
    @staticmethod
    def tag(competition):
        clean = re.sub(r'[^a-zA-Z0-9]', '', competition)
        cta = "👉 Follow FastestScore Football for instant live football match updates! ⚡"
        return f"{cta}\n\n#{clean} #Football"

    @classmethod
    def daily_fixtures(cls, date_str, league_matches):
        body = []
        for comp_name, matches in league_matches.items():
            if not matches:
                continue
            body.append(f"🏆 {comp_name.upper()}")
            for m in matches:
                body.append(f"⏰ {m['time']} | {m['home']} vs {m['away']}")
            body.append("")  # Blank line between leagues

        content = "\n".join(body).strip()
        
        return (
            f"📅 TODAY'S MATCH SCHEDULE\n"
            f"📆 {date_str}\n\n"
            f"{content}\n\n"
            f"⚽ Drop your match predictions below! 👇\n\n"
            f"{cls.tag('MatchDay')}"
        )

    @classmethod
    def lineups(cls, comp_name, home, away, rosters_text):
        return (
            f"📋 LINEUPS CONFIRMED\n"
            f"🏆 {comp_name}\n\n"
            f"{home} vs {away}\n\n"
            f"{rosters_text}\n\n"
            f"⚽ Kick-off approaching!\n\n"
            f"{cls.tag(comp_name)}"
        )

    @classmethod
    def kickoff(cls, comp_name, home, away):
        return (
            f"🟢 KICK-OFF!\n"
            f"🏆 {comp_name}\n\n"
            f"{home} 0-0 {away}\n\n"
            f"The match is underway! ⏱️\n\n"
            f"{cls.tag(comp_name)}"
        )

    @classmethod
    def goal(cls, comp_name, home, away, h_sc, a_sc, goal_info, assist):
        assist_line = f"\n🎯 Assist: {assist}" if assist else ""
        return (
            f"🚨 GOAL! GOAL GOAL\n"
            f"🏆 {comp_name}\n\n"
            f"{home} {h_sc}-{a_sc} {away}\n\n"
            f"⚽ {goal_info}"
            f"{assist_line}\n\n"
            f"{cls.tag(comp_name)}"
        )

    @classmethod
    def fulltime(cls, comp_name, home, away, h_sc, a_sc):
        return (
            f"⛳ FULL TIME\n"
            f"🏆 {comp_name}\n\n"
            f"{home} {h_sc}-{a_sc} {away}\n\n"
            f"{cls.tag(comp_name)}"
        )


#========================================
# ESPN MULTI-LEAGUE LIVE ENGINE (NINJA EDIT)
#========================================
class MultiLeagueBot:

    def __init__(self):
        self.token = os.environ.get("FB_TOKEN")
        self.fb_url = "https://graph.facebook.com/v19.0/me/feed"
        self.poll_interval = 12

        self.session = requests.Session(impersonate="chrome")
        self.db_lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=7)

        self.leagues = {
            "Champions League": "uefa.champions",
            "Europa League": "uefa.europa",
            "Conference League": "uefa.europa.conf",
            "UEFA Super Cup": "uefa.super_cup",
            "Premier League": "eng.1",
            "FA Cup": "eng.fa",
            "Carabao Cup": "eng.league_cup",
            "Community Shield": "eng.charity",
            "LaLiga": "esp.1",
            "Copa del Rey": "esp.copa_del_rey",
            "Spanish Super Cup": "esp.super_cup",
            "Serie A": "ita.1",
            "Coppa Italia": "ita.coppa_italia",
            "Italian Super Cup": "ita.super_cup",
            "Bundesliga": "ger.1",
            "DFB-Pokal": "ger.dfb_pokal",
            "German Super Cup": "ger.super_cup",
            "Ligue 1": "fra.1",
            "Coupe de France": "fra.coupe_de_france",
            "French Super Cup": "fra.super_cup",
            "Saudi Pro League": "ksa.1",
            "Saudi King's Cup": "ksa.kings.cup",
            "MLS": "usa.1",
            "U.S. Open Cup": "usa.open",
            "Leagues Cup": "concacaf.leagues.cup",
        }
        
        self.VIP_TEAMS = {
              "Saudi Pro League": ["Al Nassr"],
              "Saudi King's Cup": ["Al Nassr"],
              "MLS": ["Inter Miami"],
              "Leagues Cup": ["Inter Miami"],
        }
      
        self.db = sqlite3.connect("espn_bot_multi.db", check_same_thread=False)
        self.cursor = self.db.cursor()
        self._setup_db()

    #--------------------------------
    # Database Setup & Tracking
    #--------------------------------
    def _setup_db(self):
        with self.db_lock:
            self.cursor.execute("CREATE TABLE IF NOT EXISTS posted_goals (goal_key TEXT PRIMARY KEY)")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS match_cache (match_id TEXT PRIMARY KEY, home_team TEXT, away_team TEXT, home_score INTEGER, away_score INTEGER, status_state TEXT, competition TEXT)")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS pending_edits (post_id TEXT PRIMARY KEY, match_id TEXT, expected_goals INTEGER, slug TEXT, comp_name TEXT, home_team TEXT, away_team TEXT, h_sc INTEGER, a_sc INTEGER, attempts INTEGER)")
            self.db.commit()

    def _is_posted(self, key):
        with self.db_lock:
            return self.cursor.execute("SELECT 1 FROM posted_goals WHERE goal_key = ?", (key,)).fetchone() is not None

    def _mark_posted(self, key):
        with self.db_lock:
            self.cursor.execute("INSERT OR IGNORE INTO posted_goals (goal_key) VALUES (?)", (key,))
            self.db.commit()

    def _update_cache(self, m_id, home, away, h_sc, a_sc, state, comp_name):
        with self.db_lock:
            self.cursor.execute("""
                INSERT INTO match_cache (match_id, home_team, away_team, home_score, away_score, status_state, competition)
                VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(match_id) DO UPDATE SET
                home_score=excluded.home_score, away_score=excluded.away_score, status_state=excluded.status_state, competition=excluded.competition
            """, (m_id, home, away, h_sc, a_sc, state, comp_name))
            self.db.commit()
            
    def add_pending_edit(self, post_id, m_id, exp_goals, slug, comp_name, home, away, h_sc, a_sc):
        with self.db_lock:
            self.cursor.execute("""
                INSERT INTO pending_edits (post_id, match_id, expected_goals, slug, comp_name, home_team, away_team, h_sc, a_sc, attempts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (post_id, m_id, exp_goals, slug, comp_name, home, away, h_sc, a_sc))
            self.db.commit()

    def remove_pending_edit(self, post_id):
        with self.db_lock:
            self.cursor.execute("DELETE FROM pending_edits WHERE post_id=?", (post_id,))
            self.db.commit()

    #--------------------------------
    # Facebook API: Post & Edit
    #--------------------------------
    def post_fb(self, msg):
        for attempt in range(1, 4):
            try:
                r = self.session.post(self.fb_url, data={"message": msg, "access_token": self.token}, timeout=10)
                if r.status_code == 200:
                    post_id = r.json().get('id')
                    print(f"✅ Posted! (ID: {post_id})")
                    return post_id
                print(f"⚠️ FB Error ({attempt}/3): {r.text}")
            except Exception as e:
                print(f"⚠️ Net Error: {e}")
            time.sleep(2)
        return None
        
    def edit_fb(self, post_id, msg):
        edit_url = f"https://graph.facebook.com/v19.0/{post_id}"
        payload = {"message": msg, "access_token": self.token}
        try:
            r = self.session.post(edit_url, data=payload, timeout=10)
            if r.status_code == 200:
                print(f"🥷 NINJA EDIT SUCCESS! Added assist to post: {post_id}")
                return True
        except Exception as e:
            print(f"⚠️ Edit Error: {e}")
        return False

    #--------------------------------
    # ESPN API: Pre-Match
    #--------------------------------
    def get_lineups(self, match_id, slug):
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/summary?event={match_id}&_t={int(time.time()*1000)}"
            rosters = self.session.get(url, timeout=6).json().get("rosters", [])
            if not rosters or len(rosters) < 2:
                return None
            out = []
            for t in rosters:
                team_name = t.get('team', {}).get('displayName', 'Team')
                starters = [
                    p.get("athlete", {}).get("displayName")
                    for p in t.get("roster", [])
                    if p.get("starter") and p.get("athlete", {}).get("displayName")
                ]
                if starters:
                    out.append(f"🔹 {team_name} XI:\n" + ", ".join(starters))
            return "\n\n".join(out) if out else None
        except Exception:
            return None

    #--------------------------------
    # ESPN API: Insta-Goal Finder
    #--------------------------------
    def get_goal(self, match_id, expected_goals, slug):
        for attempt in range(1, 8):
            try:
                url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/summary?event={match_id}&_t={int(time.time()*1000)}"
                events = self.session.get(url, timeout=6).json().get("keyEvents", [])

                goal_events = [ev for ev in events if "goal" in ev.get("type", {}).get("text", "").lower()]

                if len(goal_events) < expected_goals:
                    time.sleep(5)
                    continue

                ev = goal_events[-1]
                type_text = ev.get("type", {}).get("text", "").lower()
                desc_text = ev.get("text", "") 
                is_penalty = "penalty" in type_text or "penalty" in desc_text.lower()

                clk = ev.get("clock", {}).get("displayValue", "").replace("'", "")
                scr, ast = "Unknown Player", None

                for p in ev.get("participants", []):
                    role, name = p.get("type", ""), p.get("athlete", {}).get("displayName")
                    if role == "scorer" or (not role and scr == "Unknown Player"):
                        scr = name
                    elif role == "assist":
                        ast = name

                if not ast and "ssisted by " in desc_text:
                    try:
                        ast = desc_text.split("ssisted by ")[1].split(".")[0].split(",")[0].strip()
                    except:
                        pass

                if scr != "Unknown Player" and scr is not None:
                    pen_tag = " (pen.)" if is_penalty else ""
                    return ev.get("id", f"{clk}_{scr}"), f"{scr}{pen_tag} ({clk}')", ast

            except Exception:
                pass
            time.sleep(5)

        return None, None, None

    #--------------------------------
    # The Background Assist Hunter
    #--------------------------------
    def process_pending_edits(self):
        with self.db_lock:
            pending = self.cursor.execute("SELECT * FROM pending_edits").fetchall()

        if not pending:
            return

        for row in pending:
            post_id, m_id, exp_goals, slug, comp_name, home, away, h_sc, a_sc, attempts = row
            
            if attempts >= 8:
                self.remove_pending_edit(post_id)
                continue
                
            try:
                url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/summary?event={m_id}&_t={int(time.time()*1000)}"
                events = self.session.get(url, timeout=6).json().get("keyEvents", [])
                goal_events = [ev for ev in events if "goal" in ev.get("type", {}).get("text", "").lower()]
                
                if len(goal_events) >= exp_goals:
                    ev = goal_events[-1]
                    desc_text = ev.get("text", "")
                    scr, ast = "Unknown Player", None
                    
                    for p in ev.get("participants", []):
                        role, name = p.get("type", ""), p.get("athlete", {}).get("displayName")
                        if role == "scorer" or (not role and scr == "Unknown Player"):
                            scr = name
                        elif role == "assist":
                            ast = name
                            
                    if not ast and "ssisted by " in desc_text:
                        try:
                            ast = desc_text.split("ssisted by ")[1].split(".")[0].split(",")[0].strip()
                        except:
                            pass
                            
                    if ast:
                        clk = ev.get("clock", {}).get("displayValue", "").replace("'", "")
                        type_text = ev.get("type", {}).get("text", "").lower()
                        is_penalty = "penalty" in type_text or "penalty" in desc_text.lower()
                        pen_tag = " (pen.)" if is_penalty else ""
                        g_info = f"{scr}{pen_tag} ({clk}')"
                        
                        new_msg = PostBuilder.goal(comp_name, home, away, h_sc, a_sc, g_info, ast)
                        if self.edit_fb(post_id, new_msg):
                            self.remove_pending_edit(post_id)
                            continue
                            
            except Exception:
                pass
                
            with self.db_lock:
                self.cursor.execute("UPDATE pending_edits SET attempts = attempts + 1 WHERE post_id=?", (post_id,))
                self.db.commit()

    #--------------------------------
    # Morning Engine: Daily Fixtures
    #--------------------------------
    def check_daily_fixtures(self):
        # Target Timezone: WAT (UTC+1)
        wat = timezone(timedelta(hours=1))
        now_wat = datetime.now(wat)

        # Only post once it's morning (7:00 AM onwards)
        if now_wat.hour < 7:
            return

        date_key = now_wat.strftime("%Y%m%d")
        fixture_tag = f"fixtures_{date_key}"

        # Check database: already posted today?
        if self._is_posted(fixture_tag):
            return

        print(f"☀️ Compiling Morning Fixture Digest for {now_wat.strftime('%A, %d %B %Y')}...")
        league_matches = {}
        total_games = 0

        for comp_name, slug in self.leagues.items():
            try:
                url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={date_key}&_t={int(time.time()*1000)}"
                data = self.session.get(url, timeout=8).json()
                events = data.get("events", [])
            except Exception:
                continue

            matches_list = []
            for e in events:
                comp = e.get("competitions", [])[0] if e.get("competitions") else {}
                home, away = "", ""

                for t in comp.get("competitors", []):
                    if t.get("homeAway") == "home":
                        home = t.get("team", {}).get("displayName", "Home")
                    else:
                        away = t.get("team", {}).get("displayName", "Away")

                # Apply VIP Team Filter
                if comp_name in self.VIP_TEAMS:
                    if not any(team in (home, away) for team in self.VIP_TEAMS[comp_name]):
                        continue

                # Parse Kickoff Time from ESPN's UTC ISO date
                raw_date = e.get("date", "")
                kickoff_time = "TBD"
                if raw_date:
                    try:
                        clean_iso = raw_date.replace("Z", "+00:00")
                        utc_dt = datetime.fromisoformat(clean_iso)
                        local_dt = utc_dt.astimezone(wat)
                        kickoff_time = local_dt.strftime("%H:%M WAT")
                    except Exception:
                        kickoff_time = "TBD"

                matches_list.append({
                    "home": home,
                    "away": away,
                    "time": kickoff_time
                })

            if matches_list:
                league_matches[comp_name] = matches_list
                total_games += len(matches_list)

        if total_games > 0:
            date_display = now_wat.strftime("%A, %d %B %Y")
            msg = PostBuilder.daily_fixtures(date_display, league_matches)
            print(f"\n{'-'*45}\n{msg}\n{'-'*45}")

            post_id = self.post_fb(msg)
            if post_id:
                self._mark_posted(fixture_tag)
                print(f"✅ Daily Fixture Schedule posted successfully! (ID: {post_id})\n")
        else:
            print("ℹ️ No tracked matches scheduled for today.")

    #--------------------------------
    # Main Engine: Process Single League
    #--------------------------------
    def scan_league(self, comp_name, slug, first_run):
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?_t={int(time.time()*1000)}"
            events = self.session.get(url, timeout=8).json().get("events", [])
        except Exception as e:
            print(f"⚠️ ESPN Timeout ({comp_name}): {e}")
            return

        for e in events:
            m_id = str(e.get("id"))
            state = e.get("status", {}).get("type", {}).get("state")

            comp = e.get("competitions", [])[0] if e.get("competitions") else {}
            home, away, h_sc, a_sc = "", "", 0, 0

            for t in comp.get("competitors", []):
                if t.get("homeAway") == "home":
                    home, h_sc = t.get("team", {}).get("displayName", "Home"), int(t.get("score", 0))
                else:
                    away, a_sc = t.get("team", {}).get("displayName", "Away"), int(t.get("score", 0))

            # VIP TEAM FILTER
            if comp_name in self.VIP_TEAMS:
                 if not any(team in (home, away) for team in self.VIP_TEAMS[comp_name]):
                    continue

            with self.db_lock:
                cached = self.cursor.execute("SELECT home_score, away_score, status_state FROM match_cache WHERE match_id=?", (m_id,)).fetchone()

            if first_run or not cached:
                self._update_cache(m_id, home, away, h_sc, a_sc, state, comp_name)
                continue

            ch_sc, ca_sc, c_state = cached

            # 1. Lineups
            if state == "pre" and not self._is_posted(f"{m_id}_Lineup"):
                lineups = self.get_lineups(m_id, slug)
                if lineups:
                    msg = PostBuilder.lineups(comp_name, home, away, lineups)
                    post_id = self.post_fb(msg)
                    if post_id:
                        self._mark_posted(f"{m_id}_Lineup")

            # 2. Kickoff
            if state == "in" and c_state == "pre" and not self._is_posted(f"{m_id}_KO"):
                msg = PostBuilder.kickoff(comp_name, home, away)
                post_id = self.post_fb(msg)
                if post_id:
                    self._mark_posted(f"{m_id}_KO")

            # 3. VAR Correction
            if h_sc < ch_sc or a_sc < ca_sc:
                print(f"⚠️ [VAR CORRECTION - {comp_name}] Score dropped: {home} {h_sc}-{a_sc} {away}")
                self._update_cache(m_id, home, away, h_sc, a_sc, state, comp_name)
                continue

            # 4. Live Goals (INSTA-POST)
            if h_sc > ch_sc or a_sc > ca_sc:
                print(f"\n🚨 [GOAL - {comp_name}] {home} {h_sc} - {a_sc} {away}")

                expected_total_goals = h_sc + a_sc
                e_id, g_info, ast = self.get_goal(m_id, expected_total_goals, slug)
                
                if not g_info:
                    continue

                g_key = f"{m_id}_{e_id}_{h_sc}_{a_sc}"

                if not self._is_posted(g_key):
                    msg = PostBuilder.goal(comp_name, home, away, h_sc, a_sc, g_info, ast)
                    print(f"\n{'-'*45}\n{msg}\n{'-'*45}")
                    
                    post_id = self.post_fb(msg)
                    if post_id:
                        self._mark_posted(g_key)
                        
                        # NINJA EDIT TRACKER: If no assist was found, add to pending edits
                        if not ast:
                            self.add_pending_edit(post_id, m_id, expected_total_goals, slug, comp_name, home, away, h_sc, a_sc)

            # 5. Full Time
            if state == "post" and c_state != "post" and not self._is_posted(f"{m_id}_FT"):
                msg = PostBuilder.fulltime(comp_name, home, away, h_sc, a_sc)
                post_id = self.post_fb(msg)
                if post_id:
                    self._mark_posted(f"{m_id}_FT")
                    print(f"\n🏁 [MATCH FINISHED - {comp_name}] {home} vs {away}")

            self._update_cache(m_id, home, away, h_sc, a_sc, state, comp_name)

    #--------------------------------
    # Runtime Loop
    #--------------------------------
    def run(self):
        print("="*60)
        print(" 🤖 ESPN MULTI-LEAGUE LIVE ENGINE (NINJA EDIT PRO)")
        print(" ⚡ SPEED: Insta-Post Active. Edits loaded in background.")
        print(f" 🏆 TRACKING: {len(self.leagues)} Major Competitions")
        print("="*60)

        # 1. Check for morning fixtures on startup
        self.check_daily_fixtures()

        # 2. Initial cache sync
        futures = [self.executor.submit(self.scan_league, name, slug, True) for name, slug in self.leagues.items()]
        for future in as_completed(futures):
            future.result()

        print(" ✅ Sync complete! Radar active.\n")

        # 3. Continuous monitoring loop
        while True:
            try:
                # Check for morning fixture schedule once per loop
                self.check_daily_fixtures()

                # Check all matches for score changes
                futures = [self.executor.submit(self.scan_league, name, slug, False) for name, slug in self.leagues.items()]
                for future in as_completed(futures):
                    future.result()
                    
                # Check pending edits for delayed assist data
                self.process_pending_edits()
                
            except Exception as e:
                print(f"⚠️ Master Loop Error: {e}")
            time.sleep(self.poll_interval)


app = Flask(__name__)

@app.route('/')
def home():
    return "FastestScore Bot is alive and running!", 200

def run_bot_in_background():
    bot = MultiLeagueBot()
    bot.run()

if __name__ == "__main__":
    # 1. Start your ESPN Bot loop inside a background thread
    threading.Thread(target=run_bot_in_background, daemon=True).start()
    
    # 2. Start the web server on the port Render assigns
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
