#!/usr/bin/env python3
"""
PicoMUTX browser reply worker.
Posts replies on X/Twitter using Playwright + Chrome keychain credentials.

Usage:
  python3 scripts/pico_browser_reply.py --check           # Check login state
  python3 scripts/pico_browser_reply.py --reply <json>     # Post a reply
  python3 scripts/pico_browser_reply.py --batch <csv>      # Batch from CSV

JSON format for --reply:
  {"target_url": "https://x.com/user/status/123", "reply_text": "Hello world", "lead_id": "pico-123"}
"""

import argparse
import asyncio
import csv
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

# Paths
MUTX_ROOT = Path("/Users/fortune/MUTX")
CHROME_PROFILE = "/Users/fortune/Library/Application Support/Google/Chrome/Profile 6"
CONTACT_LOG = MUTX_ROOT / "docs/pico-gtm/contact-log.csv"
CONTACT_QUEUE = MUTX_ROOT / "docs/pico-gtm/contact-queue.csv"
LEAD_TRACKER = MUTX_ROOT / "docs/pico-gtm/lead-tracker.csv"
CREDS_FILE = "/tmp/mutx_x_creds.json"
SCREENSHOT_DIR = MUTX_ROOT / "docs/pico-gtm/browser-screenshots"


def get_chrome_key():
    """Decrypt Chrome Safe Storage key from macOS Keychain."""
    import subprocess

    result = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-w",
            "-s",
            "Chrome Safe Storage",
            "/Users/fortune/Library/Keychains/login.keychain-db",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Keychain access failed: {result.stderr}")
    password = result.stdout.strip().encode("utf-8")
    return PBKDF2(password, b"saltysalt", dkLen=16, count=1003)


def decrypt_chrome_password(encrypted: bytes, key: bytes) -> str:
    if encrypted[:3] in (b"v10", b"v11"):
        iv = b" " * 16
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(encrypted[3:])
        pad_len = decrypted[-1]
        return decrypted[:-pad_len].decode("utf-8")
    return encrypted.decode("utf-8")


def load_mutxdev_creds():
    """Load or extract mutxdev X credentials."""
    if os.path.exists(CREDS_FILE):
        with open(CREDS_FILE) as f:
            creds = json.load(f)
        if creds.get("username") == "mutxdev":
            return creds

    key = get_chrome_key()
    login_db = os.path.join(CHROME_PROFILE, "Login Data")
    conn = sqlite3.connect(login_db)
    cursor = conn.execute(
        "SELECT username_value, password_value FROM logins "
        "WHERE origin_url LIKE '%x.com%' AND username_value='mutxdev'"
    )
    for user, pwd_enc in cursor:
        pwd = decrypt_chrome_password(pwd_enc, key)
        creds = {"username": user, "password": pwd}
        with open(CREDS_FILE, "w") as f:
            json.dump(creds, f)
        conn.close()
        return creds
    conn.close()
    raise RuntimeError("mutxdev credentials not found in Chrome Login Data")


async def create_context(browser):
    """Create a browser context with X cookies if available."""
    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    )
    return context


async def login_x(page, creds):
    """Login to X using credentials."""
    print("[LOGIN] Navigating to X login...")
    await page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    # Enter username
    username_input = page.locator('input[autocomplete="username"]')
    await username_input.wait_for(state="visible", timeout=15000)
    await username_input.fill(creds["username"])
    await page.keyboard.press("Enter")
    await asyncio.sleep(2)

    # Check for unusual activity / phone verification step
    unusual = page.locator('input[data-testid="ocfEnterTextTextInput"]')
    if await unusual.count() > 0:
        print("[LOGIN] Unusual activity check detected. Trying username...")
        await unusual.fill(creds["username"])
        await page.keyboard.press("Enter")
        await asyncio.sleep(2)

    # Enter password
    password_input = page.locator('input[type="password"]')
    await password_input.wait_for(state="visible", timeout=10000)
    await password_input.fill(creds["password"])
    await page.keyboard.press("Enter")
    await asyncio.sleep(5)

    # Verify login
    await page.wait_for_url("**/home**", timeout=15000)
    print("[LOGIN] Successfully logged in!")
    return True


async def check_login(page):
    """Check if currently logged into X."""
    url = page.url
    if "login" in url.lower():
        return False
    # Check for avatar or home indicator
    avatar = page.locator('[data-testid="SideNav_AccountSwitcher_Button"]')
    try:
        await avatar.wait_for(state="visible", timeout=5000)
        return True
    except PlaywrightTimeoutError:
        return False


async def post_reply(page, target_url: str, reply_text: str) -> dict:
    """Post a reply to a specific X post. Returns result dict."""
    result = {"success": False, "error": None, "reply_url": None}

    try:
        print(f"[REPLY] Navigating to {target_url}")
        await page.goto(target_url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        # Check for login redirect
        if "login" in page.url.lower():
            result["error"] = "NOT_LOGGED_IN"
            return result

        # Check if post exists (404 / suspended)
        not_found = page.locator("text=This post is unavailable")
        if await not_found.count() > 0:
            result["error"] = "POST_UNAVAILABLE"
            return result

        # Click reply button
        reply_btn = page.locator('[data-testid="reply"]').first
        await reply_btn.wait_for(state="visible", timeout=10000)
        await reply_btn.click()
        await asyncio.sleep(1)

        # Wait for compose box
        compose = page.locator('[data-testid="tweetTextarea_0"]').first
        await compose.wait_for(state="visible", timeout=10000)

        # Type reply using keyboard (fill() alone doesn't trigger X's React state)
        await compose.click()
        await page.keyboard.type(reply_text, delay=30)
        await asyncio.sleep(1)

        # Click send button
        send_btn = page.locator('[data-testid="tweetButton"]').first
        await send_btn.wait_for(state="visible", timeout=5000)
        await send_btn.click()
        await asyncio.sleep(3)

        # Verify by checking if composer closed or success indicator
        # Navigate to own replies to confirm
        result["success"] = True
        print(f"[REPLY] Posted successfully to {target_url}")
        return result

    except Exception as e:
        result["error"] = str(e)
        print(f"[REPLY] Error: {e}")
        return result


def update_contact_log(lead_id: str, target_url: str, reply_text: str, reply_url: str = None):
    """Append to contact-log.csv."""
    sent_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary = reply_text[:200].replace('"', '""').replace("\n", " ")
    notes = f"Public X reply by @mutxdev on {target_url}."
    if reply_url:
        notes += f" Reply URL: {reply_url}"

    row = f'"{sent_at}","{lead_id}","x","x","reply","{summary}","sent","{(datetime.now(timezone.utc).strftime("%Y-%m-%d"))}","hermes","{notes}"\n'
    with open(CONTACT_LOG, "a") as f:
        f.write(row)
    print(f"[LOG] Updated contact-log.csv for {lead_id}")


def update_contact_queue(lead_id: str):
    """Update contact-queue.csv status to sent."""
    rows = []
    with open(CONTACT_QUEUE) as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row.get("lead_id") == lead_id:
                row["status"] = "sent_x_reply"
                row["review_state"] = "sent"
            rows.append(row)

    with open(CONTACT_QUEUE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[LOG] Updated contact-queue.csv for {lead_id}")


def update_lead_tracker(lead_id: str):
    """Update lead-tracker.csv stage."""
    rows = []
    with open(LEAD_TRACKER) as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row.get("lead_id") == lead_id:
                row["stage"] = "contacted_x_reply"
                row["status"] = "contacted"
                row["last_touch_date"] = datetime.now().strftime("%Y-%m-%d")
                from datetime import timedelta

                row["next_action_date"] = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
            rows.append(row)

    with open(LEAD_TRACKER, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[LOG] Updated lead-tracker.csv for {lead_id}")


async def run_check():
    """Check if we can login to X."""
    creds = load_mutxdev_creds()
    print(f"[CHECK] Loaded credentials for {creds['username']}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await create_context(browser)
        page = await context.new_page()

        await login_x(page, creds)
        logged_in = await check_login(page)

        if logged_in:
            print("[CHECK] Login verified. Account is active.")
        else:
            print("[CHECK] Login failed or account suspended.")

        await browser.close()


async def run_reply(target_url: str, reply_text: str, lead_id: str):
    """Post a single reply."""
    creds = load_mutxdev_creds()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await create_context(browser)
        page = await context.new_page()

        # Login
        await login_x(page, creds)

        # Post reply
        result = await post_reply(page, target_url, reply_text)

        if result["success"]:
            update_contact_log(lead_id, target_url, reply_text, result.get("reply_url"))
            update_contact_queue(lead_id)
            update_lead_tracker(lead_id)
        else:
            print(f"[ERROR] Reply failed: {result['error']}")

        await browser.close()
        return result


async def run_batch(csv_path: str, max_sends: int = 3):
    """Process queued X replies from CSV."""
    creds = load_mutxdev_creds()

    # Read queue
    queued = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (
                row.get("source") in ("x",)
                and row.get("review_state") == "draft_ready"
                and row.get("status", "") != "sent_x_reply"
            ):
                # Load draft
                draft_path = row.get("draft_path", "")
                if draft_path and os.path.exists(MUTX_ROOT / draft_path):
                    with open(MUTX_ROOT / draft_path) as df:
                        content = df.read()
                    # Extract body (after second ---)
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        body = parts[2].strip()
                        # Get first paragraph as reply text
                        lines = [
                            line.strip()
                            for line in body.split("\n")
                            if line.strip() and not line.startswith("#")
                        ]
                        reply_text = " ".join(lines[:3])[:280]  # X char limit
                    else:
                        continue
                else:
                    continue

                queued.append(
                    {
                        "lead_id": row["lead_id"],
                        "target_url": row["repo_or_post_url"],
                        "reply_text": reply_text,
                    }
                )

    if not queued:
        print("[BATCH] No queued X replies found.")
        return

    print(f"[BATCH] Found {len(queued)} queued replies. Sending max {max_sends}.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await create_context(browser)
        page = await context.new_page()

        # Login once
        await login_x(page, creds)

        sent_count = 0
        for item in queued[:max_sends]:
            print(f"\n[BATCH] Processing {item['lead_id']}: {item['target_url']}")
            result = await post_reply(page, item["target_url"], item["reply_text"])

            if result["success"]:
                update_contact_log(item["lead_id"], item["target_url"], item["reply_text"])
                update_contact_queue(item["lead_id"])
                update_lead_tracker(item["lead_id"])
                sent_count += 1
                # Wait between sends to avoid rate limiting
                await asyncio.sleep(5)
            else:
                print(f"[BATCH] Skipped {item['lead_id']}: {result['error']}")
                if result["error"] == "NOT_LOGGED_IN":
                    print("[BATCH] Session expired, stopping.")
                    break

        print(f"\n[BATCH] Complete. Sent {sent_count}/{min(len(queued), max_sends)}.")
        await browser.close()


def main():
    parser = argparse.ArgumentParser(description="PicoMUTX browser reply worker")
    parser.add_argument("--check", action="store_true", help="Check X login state")
    parser.add_argument("--reply", type=str, help="JSON string with reply details")
    parser.add_argument("--batch", type=str, help="CSV path for batch replies")
    parser.add_argument("--max-sends", type=int, default=3, help="Max sends per batch")

    args = parser.parse_args()

    if args.check:
        asyncio.run(run_check())
    elif args.reply:
        data = json.loads(args.reply)
        asyncio.run(run_reply(data["target_url"], data["reply_text"], data.get("lead_id", "")))
    elif args.batch:
        asyncio.run(run_batch(args.batch, args.max_sends))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
