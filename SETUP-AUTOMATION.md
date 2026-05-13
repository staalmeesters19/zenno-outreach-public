# Setup auto-refresh dashboard (one-time, ~10 min)

Het dashboard op https://staalmeesters19.github.io/zenno-outreach-public/ ververst zichzelf elke 6 uur via GitHub Actions, leest Gmail via OAuth, en pusht een vers gemaskerd `index.html` terug naar de repo. Pages serveert dat dan automatisch.

## Architectuur in één oogopslag

```
GitHub Actions cron (0:07, 6:07, 12:07, 18:07 UTC)
        │
        ▼
   refresh.py
        │
        ├─► Gmail API (read-only, OAuth refresh-token)
        │    queries: in:sent  newer_than:60d
        │             in:inbox newer_than:60d -from:me
        │
        ├─► writes data_status.json   (audit-trail, committed)
        │
        └─► invokes _build_public.py
             ├─► reads leads-{wave3,wave12,international}.csv
             ├─► merges Gmail status + manual_overrides.json
             ├─► masks emails & beslisser-namen
             └─► writes index.html + dashboard-public.html

   git add + commit + push  →  GitHub Pages rebuild  →  publieke URL is fresh
```

## Eénmalige setup

### Stap 1 — Google Cloud project + Gmail API enable (3 min)

1. Open https://console.cloud.google.com/projectcreate
2. Project-naam: `zenno-outreach-cron` (of bestaande project hergebruiken)
3. Eenmaal aangemaakt: zoek bovenin "Gmail API" → **Enable**
4. Bij OAuth consent screen (links menu):
   - User type: **External** (klik op Create)
   - App name: `Zenno Outreach Cron`
   - User support email: `staalmeesters19@gmail.com`
   - Developer contact: hetzelfde
   - Scopes: kun je leeg laten (Gmail readonly is enough)
   - Test users: voeg toe **de Gmail-account waarvan de outreach verzonden is** (vermoedelijk `zennosurf@gmail.com` of `staalmeesters19@gmail.com`)
   - Save & continue helemaal door

### Stap 2 — OAuth credentials (Desktop app type) (2 min)

1. Links menu → **APIs & Services → Credentials**
2. **Create Credentials → OAuth client ID**
3. Application type: **Desktop app**
4. Name: `zenno-cron-desktop`
5. Klik **Create**, dan **Download JSON**
6. Hernoem het bestand naar `credentials.json` en plaats in deze folder (`public-deploy/`)

> `credentials.json` is door `.gitignore` uitgesloten — committen kan niet per ongeluk.

### Stap 3 — Lokaal refresh-token genereren (1 min)

Vanuit `public-deploy/`:

```powershell
pip install google-auth-oauthlib google-api-python-client
python get_refresh_token.py
```

Browser opent → kies de Gmail-account (`zennosurf@gmail.com`) → "Continue" door de "unverified app" warning ("Advanced → Go to ...") → Allow → tab sluit zichzelf.

Terminal print drie waarden:

```
GMAIL_REFRESH_TOKEN: 1//0g...
GMAIL_CLIENT_ID:     12345-abc.apps.googleusercontent.com
GMAIL_CLIENT_SECRET: GOCSPX-...
```

### Stap 4 — GitHub Secrets configureren (1 min)

1. Open https://github.com/staalmeesters19/zenno-outreach-public/settings/secrets/actions
2. **New repository secret** drie keer:
   - Name: `GMAIL_REFRESH_TOKEN`     · Value: (refresh-token uit stap 3)
   - Name: `GMAIL_CLIENT_ID`         · Value: (client-id)
   - Name: `GMAIL_CLIENT_SECRET`     · Value: (client-secret)

Geen typo's — copy/paste rechtstreeks uit de terminal.

### Stap 5 — Eerste test-run handmatig triggeren (1 min)

1. Open https://github.com/staalmeesters19/zenno-outreach-public/actions
2. Klik in de linkerkolom op **Refresh Dashboard**
3. Rechtsboven: **Run workflow** → branch `main` → **Run workflow**
4. Refresh, klik op de net-gestarte run, klik op de `refresh` job, vouw "Run refresh" open
5. Verwacht: log met `Found N sent, M inbox messages`, daarna `Written: index.html`, daarna `Auto-refresh dashboard ...` commit OF `No changes to commit`
6. Check `https://staalmeesters19.github.io/zenno-outreach-public/` — refresh-stamp onderaan moet de huidige UTC-tijd zijn

Klaar. Vanaf nu draait dit elke 6 uur op `0:07, 6:07, 12:07, 18:07 UTC` (= NL zomertijd `2:07, 8:07, 14:07, 20:07`).

## Manuele overrides — voor next-action notes die Gmail niet kan afleiden

`manual_overrides.json` in deze folder bevat per-lead override-velden die de auto-detectie níet overschrijven. Voorbeeld:

```json
{
  "info@zestfamily.it": {
    "next_action": "URGENT — tarieven sturen 13/5"
  },
  "info@surfschoolcastricum.com": {
    "next_action": "Donderdag bellen — tel 0642206839"
  }
}
```

Workflow voor een nieuwe note:
1. Edit `manual_overrides.json`
2. `git add manual_overrides.json && git commit -m "Update notes for X" && git push`
3. De cron pakt de override de eerstvolgende run mee — of trigger meteen handmatig via Actions UI

## Onderhoud

| Wat | Wanneer | Hoe |
|---|---|---|
| OAuth verifying app warning verdwijnt | Google Cloud → OAuth consent → publiceer | Optioneel, alleen jij gebruikt het |
| Refresh-token werkt niet meer | Na 6 maanden inactiviteit OF wachtwoord-reset | Herhaal stap 3 + 4 |
| Cron pauzeren | Bv. tijdens vakantie | GitHub Actions → Refresh Dashboard → "..." → Disable workflow |
| CSV's bijwerken | Nieuwe wave / lead-additions | Edit lokaal, commit, push — cron pikt automatisch op |
| Lookback-window aanpassen | Nu 60d (zie `LOOKBACK_DAYS` in `refresh.py`) | Edit + commit |

## Troubleshooting

**Workflow faalt met `Missing env vars`** → secrets niet correct ingesteld. Check de exact-spelling (`GMAIL_REFRESH_TOKEN`, niet `GMAIL_TOKEN`).

**Workflow faalt met `invalid_grant`** → refresh-token verlopen / ingetrokken. Run stap 3 opnieuw en update de secret.

**Index ververst niet visueel** → CDN-cache. Hard-refresh in browser (Ctrl+Shift+R) of wacht ~5 min. GitHub Pages serveert via Fastly.

**Workflow draait, maar `No changes to commit`** → normaal als er sinds laatste run niks veranderd is in Gmail. Pages-content blijft up-to-date.

**Verkeerde Gmail-account geauthenticeerd** → run `python get_refresh_token.py` opnieuw, kies juiste account, vervang secret.

## Security checklist

- [x] `credentials.json` in `.gitignore`
- [x] Refresh-token alleen in GitHub Secrets (encrypted at rest)
- [x] Scope is `gmail.readonly` — script kan geen mail sturen of verwijderen
- [x] Workflow heeft `contents: write` permission, geen secrets-export
- [x] HTML is gemaskerd: geen real emails, beslisser-namen → initialen
- [x] Repo public, maar dashboard heeft `<meta name="robots" content="noindex,nofollow">`
