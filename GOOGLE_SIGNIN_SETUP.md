# Google sign-in for NAB and the phone app (free)

Google needs two "OAuth client IDs" from one free Google Cloud project. Nobody is charged.

## One-time, in Google Cloud Console (console.cloud.google.com)
1. Use your existing project (the one with the Drive service account) or create a new one.
2. APIs & Services > OAuth consent screen: User type External, app name "NAB", your email. Leave it in Testing and add every person's Gmail under "Test users" (up to 100). No Google review is needed this way.
3. APIs & Services > Credentials > Create credentials > OAuth client ID:
   - **Desktop app** (for NAB on Windows). Copy the Client ID and Client secret.
   - **Web application** (for the phone). Under "Authorised JavaScript origins" add `https://nab-cloud-bot.onrender.com`. Copy the Client ID (no secret needed).

## In NAB (owner PC)
Settings > Accounts > Google sign-in: paste the Desktop Client ID and secret, Save. In the People table, type each person's Google email on their row. The sign-in screen then shows "Sign in with Google".

## On Render (nab-bot service) > Environment
- `GOOGLE_CLIENT_ID` = the Web Client ID.
- Optional `ALLOWED_EMAILS` = comma-separated Gmail addresses that may use the phone without a NAB account.

The phone shows the Google button only when `GOOGLE_CLIENT_ID` is set. Any Gmail can join; a switched-off or blocked email (NAB, or `BLOCKED_EMAILS` on Render) is refused. The phone's plain "type your name" sign-in still works next to it.
