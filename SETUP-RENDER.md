# Render Cron Setup — Auto-refresh elke 6 uur

## Eenmalig (~12 min totaal)

### Stap 1: Google Cloud OAuth (5 min)

1. Ga naar https://console.cloud.google.com/projectcreate
2. Maak project "Zenno Outreach Refresh"
3. APIs & Services → Library → zoek "Gmail API" → Enable
4. APIs & Services → OAuth consent screen:
   - User Type: External
   - App name: Zenno Outreach Refresh
   - Support email: zennosurf@gmail.com (of jouw)
   - Save (skip rest)
   - Add test user: zennosurf@gmail.com
5. APIs & Services → Credentials → Create Credentials → OAuth client ID:
   - Application type: Desktop app
   - Name: Zenno Refresh Local
   - Download JSON → rename naar `credentials.json` in `public-deploy/` folder

### Stap 2: Lokaal refresh-token genereren (1 min)

```bash
cd public-deploy
pip install google-auth-oauthlib google-api-python-client
python get_refresh_token.py
```

Browser opent → log in met `zennosurf@gmail.com` → bij "App not verified" → Advanced → Go to ... → Allow.

Output bevat 3 waarden. Kopieer ze.

### Stap 3: GitHub Personal Access Token (2 min)

Voor git push vanuit Render Cron Job heb je een PAT nodig.

1. Ga naar https://github.com/settings/personal-access-tokens/new
2. Token name: "Zenno Refresh Bot"
3. Repository access: Only select repositories → `zenno-outreach-public`
4. Permissions → Repository permissions:
   - Contents: Read and write
   - Metadata: Read-only (auto)
5. Generate token → kopieer (begin met `github_pat_...`)

### Stap 4: Render Cron Job aanmaken (3 min)

1. Ga naar https://dashboard.render.com/
2. New → Cron Job (NIET Web Service)
3. Connect GitHub: kies repo `staalmeesters19/zenno-outreach-public`
4. Settings:
   - **Name**: zenno-dashboard-refresh
   - **Region**: Frankfurt
   - **Branch**: main
   - **Root Directory**: (leeg)
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Schedule**: `7 */6 * * *` (elke 6 uur, op minuut 7)
   - **Command**: `python refresh.py`
5. **Environment Variables** (klik Advanced → Add Environment Variable):
   - `GMAIL_REFRESH_TOKEN` = (uit Stap 2)
   - `GMAIL_CLIENT_ID` = (uit Stap 2)
   - `GMAIL_CLIENT_SECRET` = (uit Stap 2)
   - `GITHUB_TOKEN` = (uit Stap 3 — de PAT)
   - `GIT_USER_EMAIL` = `zennosurf-bot@github-actions`
   - `GIT_USER_NAME` = `Zenno Refresh Bot`
6. Create Cron Job → Render bouwt de eerste keer

### Stap 5: Manual trigger test (1 min)

In Render dashboard → klik op zenno-dashboard-refresh → "Trigger Run" knop rechtsboven.

Wacht ~30 sec → check logs voor success. Daarna check https://staalmeesters19.github.io/zenno-outreach-public/ — als er nieuwe Gmail-data was, zie je een fresh commit in de repo.

## Kosten

Render Cron Jobs = **$1/maand** voor 1 job. 4 runs/dag × 30 sec elk = ruim binnen limiet.

## Troubleshooting

- **OAuth error "invalid_grant"** → refresh-token verlopen (gebeurt zelden); re-run Stap 2
- **Git push fails** → check PAT permissions, moet "Contents: Read and write" op specifieke repo
- **Geen veranderingen detecteerd** → check `data_status.json` diff in repo na een run
- **Manual override** voor specifieke leads: edit `manual_overrides.json` in repo → next run pakt het op

## Voor manual override van next_actions

Edit `manual_overrides.json`:
```json
{
  "info@zestfamily.it": {"next_action": "URGENT — tarieven sturen"},
  "info@bohemianbirds.com": {"next_action": "Dialoog loopt — Dilana info-mail"}
}
```

Commit + push naar repo. Next refresh-run pickt het op.
