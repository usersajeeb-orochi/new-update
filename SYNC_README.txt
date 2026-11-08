NAB v2.3.3 — settings sync (nothing to install or set up)

Settings sync through the same Google Drive folder NAB already uploads clips to.
It creates one small file there, nab_settings_sync.json. Every PC that already
uploads to Drive syncs automatically — no server, no keys, no extra steps.

Synced: settings/hotkeys/sliders, URL mappings, paper list, categories,
subscription dates, learned aliases, PDF Maker settings.
Stays per-PC: clip folder, daily goal/streak, PDF background image path.
Timing: checks every minute, again at close, and at startup.
Check it: click the 🔄 button (status + who changed what, when).
If two PCs edit the same group at once, the Drive copy wins and yours is
saved in Documents\nab_sync_conflicts\.

v3.0.40: owner/follower. Only the owner PC uploads; all others download only (new installs get everything automatically). Optional Settings ID = separate file nab_settings_sync_<id>.json.
