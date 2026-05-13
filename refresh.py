"""Refresh script: query Gmail, update status, rebuild masked dashboard.

Runs via Render Cron Job every 6h. After rebuilding the dashboard, auto-commits
and pushes changed files back to the GitHub repo using GITHUB_TOKEN env var.

Inputs:
  - GMAIL_REFRESH_TOKEN / GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET (env)
  - leads-wave3.csv / leads-wave12.csv / leads-international.csv
  - data_status.json (overwritten each run, keeps audit-trail in git)
  - manual_overrides.json (optional — manual next_action / notes that survive refresh)

Outputs:
  - data_status.json  (Gmail-derived status, committed)
  - index.html        (masked public dashboard, served by GitHub Pages)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).parent
LOOKBACK_DAYS = 60  # Gmail "newer_than:" window


# ----------------------------------------------------------------------------
# Gmail auth + fetch
# ----------------------------------------------------------------------------

def authenticate_gmail():
    """Build Gmail service from refresh-token stored in env."""
    missing = [k for k in ("GMAIL_REFRESH_TOKEN", "GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET") if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def fetch_messages(service, query, max_results=500):
    """Fetch messages matching query — paginates, returns list of dicts."""
    msgs = []
    page_token = None
    fetched = 0
    while True:
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=min(100, max_results - fetched), pageToken=page_token
        ).execute()
        ids = resp.get("messages", [])
        for stub in ids:
            full = service.users().messages().get(
                userId="me",
                id=stub["id"],
                format="metadata",
                metadataHeaders=["From", "To", "Cc", "Subject", "Date"],
            ).execute()
            headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
            msgs.append({
                "id": full["id"],
                "thread_id": full.get("threadId", ""),
                "labels": full.get("labelIds", []),
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "cc": headers.get("Cc", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": full.get("snippet", ""),
            })
            fetched += 1
            if fetched >= max_results:
                return msgs
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return msgs


# ----------------------------------------------------------------------------
# Classification
# ----------------------------------------------------------------------------

EMAIL_RE = re.compile(r"<([^>]+)>")
SIMPLE_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def extract_email(addr_str):
    """Extract email from 'Name <email>' or 'email' format."""
    if not addr_str:
        return ""
    m = EMAIL_RE.search(addr_str)
    if m:
        return m.group(1).strip().lower()
    m = SIMPLE_EMAIL_RE.search(addr_str)
    return (m.group(0) if m else addr_str).strip().lower()


def parse_date(date_str):
    """Parse RFC 2822 date."""
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return datetime.now(timezone.utc)


def classify_tone(subject, snippet):
    """Heuristic tone classifier (NL + EN). Returns one of:
    positive / negative / auto-reply / bounce / neutral.
    """
    s = f"{subject} {snippet}".lower()

    # Bounces — strongest signals first
    bounce_signals = [
        "address not found", "mail delivery", "mailer-daemon", "delivery status notification",
        "undeliverable", "not delivered", "delivery has failed", "could not be delivered",
        "user unknown", "no such user",
    ]
    if any(w in s for w in bounce_signals):
        return "bounce"

    # Auto-replies
    auto_signals = [
        "we are closed", "out of office", "ooo", "automatic reply", "automatisch antwoord",
        "afwezig", "onbereikbaar", "onderweg", "vakantie", "op vakantie",
        "currently away", "i am away", "back on", "weer terug",
    ]
    if any(w in s for w in auto_signals):
        return "auto-reply"

    # Negative
    negative_signals = [
        "nee dank", "nee, dank", "past niet", "helaas niet", "niet bezig", "geen interesse",
        "not interested", "decline", "won't be able", "afsluiten", "geen ruimte",
        "no thank", "no thanks",
    ]
    if any(w in s for w in negative_signals):
        return "negative"

    # Positive
    positive_signals = [
        "koffie", "bellen", "bel ", "kennis", "kennismak", "afspraak", "leuk", "tof",
        "interesse", "interessant", "tarieven", "wanneer", "langs", "kan ik",
        "calendly", "zoom", "teams", "videocall", "graag", "spreken",
        "looks good", "sounds great", "interested", "let's talk",
    ]
    if any(w in s for w in positive_signals):
        return "positive"

    return "neutral"


def is_bounce_subject(subject):
    s = (subject or "").lower()
    return any(w in s for w in [
        "address not found", "mail delivery", "undeliverable", "delivery status notification",
        "delivery failure", "returned mail",
    ])


def extract_bounced_address(snippet, body_subject):
    """Bounces from Mailer-Daemon contain the original recipient in the body —
    try to recover it so we can mark the right lead as 'bounce'."""
    text = f"{body_subject} {snippet}"
    candidates = SIMPLE_EMAIL_RE.findall(text)
    # filter out daemon/own-domain noise
    skip = ("mailer-daemon", "postmaster", "googlemail.com", "google.com", "noreply", "no-reply")
    for c in candidates:
        cl = c.lower()
        if not any(k in cl for k in skip):
            return cl
    return None


# ----------------------------------------------------------------------------
# Build status map
# ----------------------------------------------------------------------------

def build_status_map(sent_msgs, inbox_msgs, own_addresses):
    """Build status map keyed on lead email.
    - 'sent-no-reply'  if we sent but nothing came back
    - 'replied'        if a matching inbox message exists (also sets tone)
    - 'bounce'         if Mailer-Daemon bounced
    """
    status: dict[str, dict] = {}

    # 1. Sent messages → sent-no-reply (initial state per recipient)
    for m in sent_msgs:
        recipients = []
        for hdr in (m.get("to", ""), m.get("cc", "")):
            for part in hdr.split(","):
                addr = extract_email(part)
                if addr and addr not in own_addresses and "noreply" not in addr and "no-reply" not in addr:
                    recipients.append(addr)
        for addr in recipients:
            sent_dt = parse_date(m["date"])
            sent_iso = sent_dt.date().isoformat() if sent_dt else None
            existing = status.get(addr)
            if existing is None or (sent_iso and (existing.get("sent_date") or "") < sent_iso):
                status[addr] = {
                    "status": "sent-no-reply",
                    "tone": None,
                    "sent_date": sent_iso,
                    "next_action": None,
                    "reply_snippet": None,
                }

    # 2. Inbox messages → replied / bounce / auto-reply
    for m in inbox_msgs:
        from_addr = extract_email(m["from"])
        subject = m.get("subject", "")
        snippet = m.get("snippet", "")

        # Bounce: from mailer-daemon — recover original recipient
        if "mailer-daemon" in from_addr or is_bounce_subject(subject):
            bounced_addr = extract_bounced_address(snippet, subject)
            if bounced_addr and bounced_addr in status:
                status[bounced_addr].update({
                    "status": "replied",
                    "tone": "bounce",
                    "reply_snippet": (snippet or "")[:240],
                    "next_action": f"EMAIL BOUNCE — adres bestaat niet of mailbox vol.",
                })
            continue

        # Normal reply
        if from_addr and from_addr in status:
            tone = classify_tone(subject, snippet)
            status[from_addr].update({
                "status": "replied",
                "tone": tone,
                "reply_snippet": (snippet or "")[:240],
                "next_action": status[from_addr].get("next_action"),  # preserve manual override if any
            })

    return status


def merge_with_manual_overrides(auto_status, manual_path):
    """manual_overrides.json: { email: { next_action, status, tone, sent_date, ... } }
    Manual values take precedence over Gmail-derived values when non-null.
    """
    if not manual_path.exists():
        return auto_status
    try:
        manual = json.loads(manual_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  WARN: could not parse manual_overrides.json: {e}")
        return auto_status

    for email, overrides in manual.items():
        if not isinstance(overrides, dict):
            continue  # skip _comment and other non-override keys
        email = email.lower()
        auto_status.setdefault(email, {
            "status": "not-mailed",
            "tone": None,
            "sent_date": None,
            "next_action": None,
            "reply_snippet": None,
        })
        for k, v in overrides.items():
            if v is not None:
                auto_status[email][k] = v
    return auto_status


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Refresh starting...")
    svc = authenticate_gmail()

    # Resolve own address(es) so 'from:me' filter works in case alias is used.
    profile = svc.users().getProfile(userId="me").execute()
    own_email = profile.get("emailAddress", "").lower()
    own_addresses = {own_email}
    print(f"  Authenticated as: {own_email}")

    sent = fetch_messages(svc, f"in:sent newer_than:{LOOKBACK_DAYS}d", max_results=500)
    inbox = fetch_messages(svc, f"in:inbox newer_than:{LOOKBACK_DAYS}d -from:me", max_results=500)
    print(f"  Found {len(sent)} sent, {len(inbox)} inbox messages (last {LOOKBACK_DAYS}d)")

    status_map = build_status_map(sent, inbox, own_addresses)
    status_map = merge_with_manual_overrides(status_map, SCRIPT_DIR / "manual_overrides.json")

    # Stable ordering for git diffs
    sorted_status = dict(sorted(status_map.items()))
    status_path = SCRIPT_DIR / "data_status.json"
    status_path.write_text(json.dumps(sorted_status, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"  Wrote {len(sorted_status)} entries to data_status.json")

    # Tallies
    by_status = {}
    for v in sorted_status.values():
        key = (v.get("status"), v.get("tone"))
        by_status[key] = by_status.get(key, 0) + 1
    print("  By status:")
    for (st, tn), n in sorted(by_status.items(), key=lambda x: (-x[1], str(x[0]))):
        print(f"    {st!s:18s} tone={tn!s:12s} n={n}")

    # Rebuild masked HTML
    print("  Rebuilding masked dashboard...")
    result = subprocess.run(
        [sys.executable, "_build_public.py"],
        cwd=SCRIPT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    print(result.stdout)
    if result.returncode != 0:
        print("STDERR:", result.stderr, file=sys.stderr)
        raise RuntimeError("Build failed")

    print(f"[{datetime.now(timezone.utc).isoformat()}] Refresh complete.")


def git_push_if_changed():
    """Auto-commit + push if data_status.json or index.html veranderde."""
    repo_dir = SCRIPT_DIR

    # Configure git identity (Render context)
    subprocess.run(
        ["git", "config", "user.email", os.environ.get("GIT_USER_EMAIL", "bot@example.com")],
        cwd=repo_dir, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", os.environ.get("GIT_USER_NAME", "Refresh Bot")],
        cwd=repo_dir, check=True,
    )

    # Check for changes
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_dir, capture_output=True, text=True,
    )
    if not result.stdout.strip():
        print("No changes to commit.")
        return

    # Stage known output files
    for fname in ["data_status.json", "index.html", "dashboard-public.html"]:
        subprocess.run(["git", "add", fname], cwd=repo_dir)

    msg = f"Auto-refresh dashboard {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    subprocess.run(["git", "commit", "-m", msg], cwd=repo_dir, check=True)

    # Push using PAT (GITHUB_TOKEN env var)
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN env var not set — cannot push.")

    remote = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repo_dir, capture_output=True, text=True,
    ).stdout.strip()
    # https://github.com/owner/repo.git → https://x-access-token:TOKEN@github.com/owner/repo.git
    auth_remote = remote.replace("https://", f"https://x-access-token:{token}@")
    subprocess.run(["git", "push", auth_remote, "main"], cwd=repo_dir, check=True)
    print(f"Pushed: {msg}")


if __name__ == "__main__":
    main()
    git_push_if_changed()
