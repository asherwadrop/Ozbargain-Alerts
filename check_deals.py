"""
OzBargain hot deal alerts.

Every time this runs it:
  1. Reads the list of new deals from OzBargain.
  2. Finds deals that got lots of upvotes soon after being posted.
  3. Sends each one to Discord (only once per deal).
"""

import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# ---- Settings you can change ----
MIN_VOTES = 30        # how many upvotes a deal needs...
WINDOW_MINUTES = 60   # ...within this many minutes of being posted
# ---------------------------------

FEED_URL = "https://www.ozbargain.com.au/deals/feed"
SEEN_FILE = "seen.json"
OZB_NS = "{https://www.ozbargain.com.au}"
USER_AGENT = "Mozilla/5.0 (OzBargain hot deal alerts)"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def load_seen():
    try:
        with open(SEEN_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_seen(seen):
    # Only remember the most recent 500 deals so the file stays small
    with open(SEEN_FILE, "w") as f:
        json.dump(seen[-500:], f, indent=1)


def get_hot_deals(min_votes, window_minutes):
    root = ET.fromstring(fetch(FEED_URL))
    now = datetime.now(timezone.utc)
    hot = []
    for item in root.iter("item"):
        meta = item.find(OZB_NS + "meta")
        if meta is None:
            continue
        posted = parsedate_to_datetime(item.findtext("pubDate"))
        age_minutes = (now - posted).total_seconds() / 60
        votes = int(meta.get("votes-pos", 0))
        if age_minutes <= window_minutes and votes >= min_votes:
            hot.append({
                "id": item.findtext("link").rsplit("/", 1)[-1],
                "title": item.findtext("title"),
                "link": item.findtext("link"),
                "votes": votes,
                "comments": int(meta.get("comment-count", 0)),
                "age_minutes": int(age_minutes),
                "image": meta.get("image"),
            })
    return hot


def post(webhook_url, message):
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(message).encode(),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    urllib.request.urlopen(request, timeout=30)


def send_to_discord(webhook_url, deal, practice=False):
    label = "🧪 TEST: " if practice else ""
    embed = {
        "title": (label + deal["title"])[:256],
        "url": deal["link"],
        "description": (
            f"🔥 **{deal['votes']} upvotes** in {deal['age_minutes']} minutes"
            f" · 💬 {deal['comments']} comments"
        ),
        "color": 0xF58220,
    }
    if deal["image"]:
        embed["thumbnail"] = {"url": deal["image"]}
    # Plain text too, so phone notifications have something to show
    content = f"{label}🔥 {deal['votes']} votes: {deal['title']}"[:2000]
    post(webhook_url, {"content": content, "embeds": [embed]})


def main():
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        sys.exit("Missing DISCORD_WEBHOOK_URL - see the setup guide.")

    if os.environ.get("SEND_TEST") == "true":
        post(webhook_url, {"content": "✅ Your OzBargain alerts are connected!"})

    # A manual test run can use different numbers than the settings above
    min_votes = int(os.environ.get("MIN_VOTES") or MIN_VOTES)
    window_minutes = int(os.environ.get("WINDOW_MINUTES") or WINDOW_MINUTES)
    practice = (min_votes, window_minutes) != (MIN_VOTES, WINDOW_MINUTES)
    if practice:
        print(f"Practice run: {min_votes}+ votes within {window_minutes} minutes")

    seen = load_seen()
    hot_deals = get_hot_deals(min_votes, window_minutes)
    if practice:
        # Send at most 5, and don't remember them, so real alerts still work
        for deal in hot_deals[:5]:
            print(f"Practice alert: {deal['title']} ({deal['votes']} votes)")
            send_to_discord(webhook_url, deal, practice=True)
    else:
        for deal in hot_deals:
            if deal["id"] in seen:
                continue
            print(f"Alerting: {deal['title']} ({deal['votes']} votes)")
            send_to_discord(webhook_url, deal)
            seen.append(deal["id"])
    save_seen(seen)
    print(f"Checked feed: {len(hot_deals)} matching deal(s) right now.")


if __name__ == "__main__":
    main()
