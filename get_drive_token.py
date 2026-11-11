# get_drive_token.py - run ONCE on a PC to sign in as the Gmail account that owns the NAB Cloud folder.
# It writes nab_drive_user.json (keep it private: never in GitHub). See GET_DRIVE_TOKEN.md.
#   pip install google-auth-oauthlib
#   python get_drive_token.py  client_secret_XXXX.json      (the Desktop-app OAuth client file)
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]


def main():
    if len(sys.argv) < 2:
        print("Usage: python get_drive_token.py <client_secret.json>")
        return 1
    flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline",
                                  authorization_prompt_message="A browser opens: sign in as the Gmail that owns the NAB Cloud folder...")
    if not creds.refresh_token:
        print("No refresh token came back. Remove the app at myaccount.google.com/permissions and run again.")
        return 1
    data = json.loads(creds.to_json())
    with open("nab_drive_user.json", "w", encoding="utf-8") as f:
        json.dump(data, f)
    print("\nSaved nab_drive_user.json")
    print("1) Put it next to BUILD.bat (it gets packed into NAB.exe) - or in Documents for a quick test.")
    print("2) On Render, add an environment variable DRIVE_USER_JSON with the text below:\n")
    print(json.dumps(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
