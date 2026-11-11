# Fix "Service Accounts do not have storage quota"

A service account cannot create files in a normal Gmail folder. NAB and the cloud bot therefore sign in as the Gmail
that owns the folder (botmonitoringautomation) instead. One-time setup, about 5 minutes:

1. Google Cloud Console > APIs & Services > OAuth consent screen: click **Publish app** (Production).
   If you leave it in Testing the token dies after 7 days. The "not verified" warning in step 3 is normal for your own app.
2. Use the Desktop OAuth client file (client_secret_....json). Never put it in GitHub.
3. On your PC:  `pip install google-auth-oauthlib`  then  `python get_drive_token.py client_secret_XXXX.json`
   Sign in as botmonitoringautomation, press Advanced > continue, allow Drive.
4. It writes `nab_drive_user.json` and prints its text.
   - Render > nab-cloud-bot > Environment: add `DRIVE_USER_JSON` = that text. (It redeploys.)
   - Put `nab_drive_user.json` next to BUILD.bat, build NAB.exe again (it is packed inside, like the other key).
5. The folder no longer needs to be shared with the service account.
