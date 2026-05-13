"""One-off local helper: exchange OAuth consent for a long-lived refresh-token.

Run LOCALLY once. The refresh-token, client-id and client-secret printed
at the end go into the GitHub repo's Actions Secrets (see SETUP-AUTOMATION.md).

Steps:
  1. Setup Google Cloud OAuth (Desktop app type) — see SETUP-AUTOMATION.md.
  2. Download the OAuth client JSON to this folder as `credentials.json`.
  3. pip install google-auth-oauthlib google-api-python-client
  4. python get_refresh_token.py
  5. Browser opens — authorise the Gmail account that sends the outreach
     (zennosurf@gmail.com or whichever inbox the cron should read).
  6. Copy the three values into GitHub Secrets.

Security: `credentials.json` and the printed refresh-token are sensitive —
DO NOT commit them. `.gitignore` already excludes credentials.json.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

if __name__ == "__main__":
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    print("\n" + "=" * 70)
    print("Kopieer de volgende drie waarden naar GitHub repo Settings → Secrets:")
    print("=" * 70)
    print(f"\nGMAIL_REFRESH_TOKEN:\n{creds.refresh_token}\n")
    print(f"GMAIL_CLIENT_ID:\n{creds.client_id}\n")
    print(f"GMAIL_CLIENT_SECRET:\n{creds.client_secret}\n")
    print("=" * 70)
    print("Refresh-tokens vervallen NIET zolang ze blijven werken (Google policy).")
    print("Bewaar credentials.json lokaal — niet committen.")
    print("=" * 70)
