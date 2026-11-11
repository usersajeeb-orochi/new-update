v3.0.54
  * Phone clips know which day's paper they are for. When you press Use on a clip from another day, NAB switches its date to that day and tells you. Older-day clips are listed first and tagged "Paper of <date>".
  * A paper or category typed on the phone that NAB does not have yet is tagged "New paper" / "New category". Pressing Use asks to add it to NAB first.

v3.0.53
  * Drag and drop, smooth: drag a layer up or down to reorder it (the others slide out of the way; Esc cancels). Drag image files, or a phone clip card, onto the canvas: it shows a drop target while you drag. Paper logos now show faded in the paper list.
  * Phone clips arrive faster: the list checks every 6 seconds and only downloads new or changed entries, a sound and pop-up announce a new clip, the cloud server is kept awake, and Ctrl+Shift+N takes the next phone clip (opens its image and fills the fields).

v3.0.52
  * Phone clips now sit on the right of the Clip screen (the separate Phone tab is gone). Telecom industry, GP, BL, Robi, Teletalk and Edotco come first, each as its own group; everything else follows, bundled by paper. Press Use to fill the clip details. The Canvas & size card moved to the bottom of that column.

v3.0.51
  * Google sign-in is now open: anyone with a Gmail can join. A first sign-in creates a viewer account (look only); the owner can change its role, switch it off, or block an email in Settings > Accounts > Google sign-in.

v3.0.50
  * Sign in with Google (free). Settings > Accounts: add each person's Google email and paste a Google Cloud client ID once (steps in GOOGLE_SIGNIN_SETUP.md). The sign-in screen then shows a Google button that opens your browser.
  * Fixed: signing in with a NAB name and password on the lock screen was being blocked before sign-in.
  * Phone app: Google sign-in button, built-in paper and category lists until the owner PC uploads its own, separate column boxes that jump on after one digit, a smaller letter row, and 11 recent categories.

v3.0.49
  * Riko can now do things, not only explain. Ask in plain words: "find Bank clips from Prothom Alo this week", "is everything working?", "what is waiting from the phone?", "make today's report". Riko looks things up in NAB itself and answers from what it finds.
  * Anything that makes a file (a report) waits for your Confirm button. Riko never does it alone.
  * Bangla text for the daily screens, clearer keyboard focus and screen-reader names, reduced-motion support. Settings detail text can still be English.
  * Fixed: the packaged build now includes the account, archive, health, report, schedule, phone and agent modules.

v3.0.39
  * Start-up animation: the NAB layout assembles from boxy plates (blocks slide in and lock), then the NAB mark and spinning rings appear, with synthesised assembly sounds. It plays over the loading screen, so it uses time that was waiting anyway; if NAB needs longer, it holds on "finishing startup". Any key or click skips it.
  * NAB now opens full screen. F11 switches full screen on and off at any time.
  * Settings > Comfort > Start-up: turn the animation, its sound, or full-screen start on or off.
  * The animation is drawn in code (nab_ui\intro.html): no video file, nothing extra to download. Uses the Bahnschrift font that ships with Windows 10/11.

v3.0.38
  * Send clips to WhatsApp (free, no API): Recent saves > WhatsApp button on any clip, or Ctrl+K > "WhatsApp setup". Link once by scanning the QR code (WhatsApp > Linked devices); after that NAB sends through a hidden browser.
  * Works for groups (type the exact group name) and for a phone number with country code (your own number or anyone). Default chat, a different chat per category, send as file (full quality) or as picture, caption = file name.
  * Optional "send every saved clip automatically" (off by default).
  * Unofficial automation (WhatsApp Web): keep it to a few clips a day, ideally with a spare number. If WhatsApp changes its page and sending fails, Documents\NAB_WhatsApp\last_error.png shows what NAB saw.
  * Needs Playwright (already used by the Screenshot Bot) and Chrome or Edge.

v3.0.37
  * News Hunter is now a screen inside NAB (rail: Hunter). Each client has its own keyword set (any / all / never), look-back hours, sources, languages, repeat schedule and outputs (text file and/or Telegram).
  * Accuracy: Bangladesh-only filter from NewsBot (trusted .bd outlets, foreign and wrong "tower" stories such as Eiffel / control tower / high-rise fires dropped, Bangla-aware matching, Strict / Balanced / Wide). Built-in "Edotco / mobile towers" client with the NewsBot keyword list. Groq double-checks doubtful headlines and joins the same story told in Bangla and English.
  * Automation: "Auto" runs every client on its own schedule while NAB is open; each run writes a txt digest and/or sends a Telegram digest. Only new links are reported.
  * Speed: sources and keyword chunks are fetched in parallel; long keyword lists are split into several short searches.
  * Screenshots: tick results and press "Send selected to Screenshot Bot" (screenshots then flow into the PR Value Calculator Online tab).
  * Find similar: paste a headline/article and get the same story and follow-ups from other sites.
  * Fixed BUILD.bat: it was missing the AI, Riko, Screenshot Bot and PR modules (they would not have been inside NAB.exe).

v3.0.36
  * AI (Groq): Settings > AI holds the keys (several keys rotate when one is rate-limited), model names and a test button. Every AI feature has a normal fallback when AI is off or offline.
  * Riko / Sajeeb is now a guide: right-click her for Chat, a tip, "what have you learned" and quiet mode. She knows the whole app (riko_knowledge.md - edit it any time) and the current screen state, and she learns: tell her how you work (or type "remember: ...") and the notes appear under What have you learned, where you can delete any of them.
  * PR Value Calculator: drop images (print clips, website screenshots) or TV videos on each tab. Online = pixel width x height read from the image; Print = col x inch exact from NAB file names, estimated from your inch calibration otherwise; TV = video length in seconds. AI recognises the media name and page; "AI summary" writes the report paragraph.
  * Screenshot Bot: three attempts per link (slower each time), partial pages are used instead of failing, blank/blocked pages are detected, Google News links are followed to the real article, failure reasons are shown in plain words.

v3.0.35
  * Metadata (category + Page / Position / Size) is now one shared state: the app and the mini overlay always show the same thing, both ways, instantly.
  * Esc deselects the armed category in the app and in the overlay (and clears it everywhere).
  * Overlay now calculates size like the app: Size width follows the Position columns, and an "approx. inches" chip with a Use size button.
  * Delete a wrongly grabbed clip at once: trash button (app dock + overlay thumbnail) and Ctrl+Delete (Ctrl+Shift+Delete = all clips). Ctrl+Z brings it back. Rebindable in Settings > Hotkeys.
  * Reopening a saved clip now removes the old logo/header band automatically and fills paper, page, position, size and category.
  * Riko roams the whole window (no more top-of-screen bias), random idle spots, random start position, ledges across the page area.
  * Speed / stuck fixes: preview no longer holds the document lock while rendering, typing in Page/Position re-renders less often, overlay polling slower, browser address-bar reading can no longer freeze the clipboard monitor.
  * New tools: Screenshot Bot (was Nitro PR Engine) and PR Value Calculator (was PR_Value_Calculator.xlsx) with automatic rate lookup, import from saved clips / screenshots, xlsx export.
  * Removed unused window helpers and a dead mail function; added a polish stylesheet.
  * Install for the new tools:  pip install openpyxl playwright playwright-stealth   (Chrome or Edge is used; otherwise: playwright install chromium)

NAB 3.0.0
BUILD: put app_icon.ico, Logos\ (and canvas_bg.png if you use it) next to BUILD.bat, run BUILD.bat. The Google key
file in this folder is bundled INTO NAB.exe. KEEP THIS FOLDER PRIVATE - never push it to GitHub or share the zip.
Release: tag v3.0.0, upload build_output\NAB.exe and nab_updater.exe.
If the new window ever fails to open, NAB falls back to the old window by itself. Manual: NAB.exe --classic
Switch NAB <-> browser: Ctrl+Alt+N. Mini overlay appears when NAB is minimized (button in the top bar toggles it).


=== v3.0.1 ===
- Tracker, Subscriptions, PDF Maker and OCR Search are now screens inside the app (left rail), same look and speed. No Tk windows.
- Tracker end-of-day prompt appears when you close NAB; subscription reminder shows once a day at startup.
- Canvas + Move tool, size panel, separate Page/Position/Size boxes with auto-jump (Position jumps when "1-3" is complete, Size on Enter or after typing a valid size).
- PDF Maker runs in a thread pool inside NAB (no second process). Settings tab edits the same nab_pdf_config.json.
- OCR Search needs Tesseract installed (UB-Mannheim build, tick Bengali). Index: Documents\nab_ocr_index.json.
- Batch mode is still the classic window:  NAB.exe --classic
- KEEP THIS ZIP PRIVATE: it contains the Google key. Never push it to GitHub. Release: tag v3.0.1 with NAB.exe + nab_updater.exe.
- If paper detection misbehaves: Settings > Detection shows what the monitor sees (tab title, URL, clipboard).
- Added after audit: Levels dialog (brightness/contrast/gamma), Magic wand (W; Shift+click = wider), Settings > Upload older days, Ctrl+K entries open in-app screens.
- Not ported from classic: canvas background image picker, right-click category menu (use Settings > Categories), Batch mode (NAB.exe --classic).
- IMPORTANT: put your Logos folder (Daily Star.png, TBS.png ...) next to BUILD.bat before building. The zip's Logos folder is empty. BUILD.bat warns if it is.

=== Build 3 (13 Oct) ===
- Position and Size are now two one-digit boxes each: type 1 then 5 -> "1-5"; 2 then 7 -> "2x7". No symbols needed. Page -> Position -> Size jump automatically; Enter on the last box saves.
- BUILD.bat: fixed the quote bug (".""=="" was unexpected"); icon is optional; installs from requirements.txt.
- Logos: your 38 logo files are in Logos\ (bundled). Settings > Newspapers shows how many were found and where it looks.
- Browser extension: RELOAD it in chrome://extensions (version 1.1). NAB's listener no longer needs the websockets package.
  Settings > Detection shows: listener status, whether a browser is connected, the last clipboard/window it saw. Log file: Documents\nab_log.txt
- Overlay is created at startup (hidden) and shown when you minimize NAB or click the overlay button.

=== Build 4 (v3.0.3) ===
* Size box: second number may be 2 digits (8x16); wider box in app and mini window.
* Papers: emojis no longer shown; semibold font. "Paste shot" button = logo from a screenshot (Win+Shift+S, then click it).
* nab_log.txt is temporary: emptied at every start, max 200 KB. Detection table keeps only the last 40 rows in memory.
* Mini window: resizable (bottom-right corner, size remembered), double-click returns to the app, empty state instead of the header page after saving.
* Clone stamp (key S): Alt+click source, paint over what to hide. Toolbar compacted so Paste is always visible.
* Settings -> About: illustrated user manual + credit.
NOTE: the zip contains the Google key file - keep it private, never push to GitHub.

=== Build 5 (v3.0.4) ===
Metadata:  Size 2nd box takes decimals (4 x 3.5) · Alt+1..9 adds more categories to one save · Ctrl+Enter / ↺ repeats the last Page-Position-Size ·
           Page is read from the ePaper tab address/title when it shows it (dashed box; per-paper pattern in Settings -> Paper defaults).
Size:      "Smart size": best JPEG quality under 500 KB (over-4 MB sources aim ~780 KB), reduces dimensions slightly only if needed; shown in the status bar.
Detection: Detection test (Ctrl+K or Settings -> Detection) · "Which paper is this?" prompt for unknown sites · extension status dot (bottom right) · first-run Setup guide.
Editor:    Invert selection (Ctrl+Shift+I) · Straighten (auto-deskew) · Remember area / Clean-up per paper · smart trim on paste (instant paste, trim runs in background)
           · Calibrate inches -> live size in inches · Ctrl+Shift+C copies the last saved clip, Ctrl+Shift+F opens its folder.
Safety:    crash-safe draft (restore offer at next start) · daily + after-update settings backups (Settings -> Backups) · 10 s undo window (Ctrl+Z).
Sync:      uploading settings needs Telegram approval (30 min per approval); downloading is free. File = nab_settings_sync.json in the built-in Drive folder.
Upload:    master switch "Upload clips to Google" (OFF by default in this build) in Settings -> Sync / General.
Comfort:   slow-PC mode (auto), overlay opacity + snap to edges, missed-save guard (taskbar flash + reminder), keyboard-focus rules, recent-saves keyboard (arrows, R retag, O open folder, Del, Enter).
Memory:    shorter undo history after saves, heavy copies released, faster first paste (cv2/numpy warmed in background).
NOTE: the zip contains the Google key file - keep it private, never push to GitHub.

=== v3.0.5 (overlay fix) ===
Overlay: clips now show (it used a stale clip count); refreshes when shown/focused and every 1.5 s; resize grip (bottom-right) and header drag now use native Windows tracking.
Clip view: the selected categories now sit big and highlighted at the top of the category list (stacked if more than one, with a pop animation).

=== v3.0.6 ===
Fixed: saving a very large clip as JPEG could fail with "broken data stream" (JPEG buffer too small). Audit: API fuzz, key/mouse fuzz of clip view, overlay, settings, tracker: no other errors found.
Selected category: big highlighted stack at top of the category list.

=== v3.0.7 ===
Duplicate names: the _2/_3 now goes at the very end ("..., Date-14-10-2026_2.jpg") so it is never confused with the Position. Retag/recent list understand it.
Motion + colours: softer blue-violet palette and gradient Save/active tools; page fade-in, modal/menu/toast pop, button hover lift and press, save-button tick, new layer / recent-save slide-in, valid-field pulse, KB count-up, overlay thumbnail fade. Only opacity/transform; off in slow-PC mode and with Windows reduce-motion.

=== v3.0.8 ===
More motion: app fade-in at start, category rows stagger in, selected category/quick-key pop, hover slide on category/layer/recent rows, nav icon bounce, new clip fades onto the canvas, floating empty-state icon, command bar scales in with staggered results, Settings pages stagger their cards, overlay category pop. All opacity/transform only, 120-350 ms; disabled in slow-PC mode and with Windows reduce-motion.

=== v3.0.9 ===
Overlay move/resize: the page no longer takes part (its mouse handler blocked the window drag). A background watcher now moves the overlay when you press on its top strip and resizes when you press the bottom-right corner (native, follows the cursor, remembers size and position).

=== v3.0.10 ===
Overlay: moving is back to the original window drag (header strip) that worked before; the bottom-right corner resizes natively (page + background watcher). Log lines "overlay: ..." in Documents\nab_log.txt show what happens when you press the corner.

=== v3.0.11 ===
Overlay ROOT CAUSE FIXED: its container shared the id "ov" with the clip-canvas layer (CSS pointer-events:none), so the whole mini window ignored the mouse (no resize, no buttons). Renamed.
Overlay: new close button (Shift+click = turn the mini window off), size button cycles Small/Medium/Large, Settings -> Comfort has "Show it when NAB is minimized" + Small/Medium/Large; resize by dragging the bottom-right corner.

=== v3.0.12 ===
Page field no longer jumps to Position by itself (main window and overlay). Tab or Enter moves on; Position still jumps to Size once it reads e.g. 1-3.

=== v3.0.13 ===
Browser extension setup: first-run question "Set up the browser extension?" -> NAB copies the bundled extension to %LOCALAPPDATA%\NAB\extension, opens Chrome/Edge/Brave on the extensions page, copies the folder path, and ticks itself green when the extension connects. Also: Settings -> About -> "Set up the extension", Ctrl+K -> "extension", Setup guide step.
The extension folder is now bundled in the EXE (BUILD.bat --add-data NAB_TabReporter). About has an illustrated tutorial (ext1-3.png) + troubleshooting. Browsers cannot install extensions silently, so the user does 3 clicks.

v3.0.14 — Riko the fox mascot (Settings → Comfort → "Riko the fox"; off by default, never on slow PCs).
  Reacts to paste, category pick, save, failed save, unsaved-clip reminder and uploads; click, tickle (4 fast clicks),
  drag and throw her; naps after 45 s. Hops into the mini window when NAB is minimized and back when restored.
  Ctrl+K: "Riko: show or hide the mascot" / "Riko: dance!". Never blocks clicks. Windows-only untested: the hop between real windows.

v3.0.15
  Riko is now a small AI: she plans routes over the app's buttons and panels (walk, jump, climb, drop), follows your cursor,
  walks to what just happened (save button, categories, status) and rests when tired. She never goes over the metadata strip
  (Page / Position / Size / Save) in the main window or the mini window.
  Suggested crop is applied automatically on paste (Settings → Clipping to turn off) and keeps a margin around the text.
  All emoji / symbol icons replaced by one set of clean icons; toolbar and small buttons are now round.

v3.0.16 — Riko is drawn pixel-exact for your screen (pre-shrunk per size/DPI), no blur from idle breathing or fractional positions.

v3.0.17 — new high-resolution Riko (20 poses): walks sideways, climbs showing her back, points at what happened, thinks, sips bubble tea, hugs a heart when tickled, sad when a save fails.

v3.0.18 — Riko: 4 outfits (Riko Blue, Snow, Shadow Cat, Neon Cat; Settings → Comfort, or Auto: she changes by herself), ~27 poses, runs on long trips, no more backward walking, cleaned sprites (no stray pieces), can stand on the top panel, standing idle pose.

v3.0.19 — Riko Plus (Settings → Riko): clip carrier (she carries the pasted clip and delivers it to Save), daily counter + goal +
  streak + milestones, smart reminders (missing category/page), Tracker deadline nudge, auto quiet mode while you clip fast,
  moods (sleepy at night, sulks if ignored, break/water reminders), special days (New Year, 21 Feb, 26 Mar, Pohela Boishakh,
  16 Dec ... + your own dates for Eid etc.), outfit unlocks (optional), mini-games (Catch Riko, Clip rain), optional sounds,
  your own lines, Bangla/English/Mixed lines, tips, stats, snack, petting, talkative level, hide/quiet timers. Ctrl+K: "Riko: ..."

v3.0.20 — Authorization + Riko Care.
  Lock screen: two ways to sign in — "Authorize by group" (request goes to the Telegram group) and "Authorize by owner" (owner's private
  chat only). Optional reason shown to the approver. Owner-only "Allow for today" remembers this PC until the set time (default 23:59).
  Quick re-login grace window after an accidental close (default 10 min). Settings → Comfort → Sign-in sets default mode, grace, time.
  Settings-sync approval stays owner-only. New file: nab_session.py (signed per-PC session file).
  Clip: Alt+] / Alt+[ (or Ctrl+K) switch the armed category and keep Page / Position / Size and your cursor.
  Riko (Settings → Riko → Care): tracker watch (papers not clipped yet), pre-save check, end-of-day wrap-up, moods that carry over
  between days, rare surprises, reacts to the chosen category (+ your own lines "Category=line"), "where was I" after a long break,
  shortcut trainer, practice mode (Ctrl+K → Riko: practice mode). Not in this build: Riko outside the NAB window (desktop pet).

v3.0.21 — Desktop pet (experimental, OFF by default; Settings → Riko → Care). A small transparent always-on-top window (150x210) where Riko
  walks along the bottom of the screen while NAB is not in front. It only covers its own footprint, never the whole screen. Hidden on
  slow-PC mode, while locked, and while the overlay is showing. New file: nab_ui/pet.html. Windows only; if the window shows a solid
  box instead of being transparent on your PC, turn the setting off and tell me.

v3.0.22 — Dark-mode fix: dropdowns, checkboxes and text boxes now follow the theme (were white / unreadable in dark). New themes based on
  Riko's skins: Riko Blue, Snow (light), Shadow Cat, Neon Cat — Settings → General → Theme, or Ctrl+K → "Theme: ...".

v3.0.23 — Send by mail (new "Mail" tab, Ctrl+K → "Open Send by mail").
  Groups (Beximco, United, Pride, BAT, Xiaomi, ASK, Telecom industry, Edotco industry are pre-made; add, edit or delete your own).
  Each group: source folders of the day, send as PDF / JPG / ZIP, "ZIP if large" (more than 20 files or 20 MB, editable globally and per group),
  To / CC / Bcc lists, ZIP name, folder name inside the ZIP, an extra file inside the ZIP (e.g. link.txt), own subject/message, on/off.
  Edotco industry = the Telecom folder zipped under the name "Edotco industry" with link.txt inside. Telecom keeps its sub-folders.
  "Prepare files" runs the existing PDF maker for PDF groups and builds the ZIPs (in <day>\OutputMail). Preview emails, Send test to me only,
  Send all (with confirm), live progress, Retry failed, send log, optional Telegram note and Bcc copy.
  Mail over the max size (default 24 MB): split into parts, or Google Drive link (Gmail only; needs link sharing allowed).
  Account: Gmail / Workspace (needs an app password, not the normal password) or any SMTP mail. The password is stored only on this PC
  (Windows DPAPI) and is never in the settings file. Export / Import of all mail settings as text. New files: nab_mailer.py, nab_mail_host.py,
  nab_ui/tool_mail.js, tool_mail.css.

v3.0.24 — Mail: Gmail app passwords typed with spaces (as Google shows them) are accepted.

v3.0.25 — Mail: choose exactly which files each group gets. In the group editor, tick a whole day folder (Beximco, United Group, ...) or only some
  items inside it, using the PDF maker's own logic: the folder's main PDF, each sub-folder PDF (Bank, Cement ...) and the combined PDFs
  (Banking & Finance, Power Energy & Mineral). A group can mix folders, e.g. United Group = its own folder + Beximco's Bank PDF.
  PDF groups get those PDFs, JPG / ZIP groups get the images or folders behind them. Mail now builds its PDFs per item, so two folders that
  have a sub-folder with the same name (e.g. Bank in Beximco and in United Group) no longer overwrite each other: the second one is named
  "... (United Group).pdf". NOTE: the stand-alone PDF maker itself still writes both to the same file name.

v3.0.26 — Mail: group editor is now PDF-first. Send as / If large are at the top; below is a searchable list of PDFs grouped by their folder,
  with "all / none" per folder. Tick exactly the PDFs a group should get (e.g. Beximco group = Bank, Economy, LNG, LPG, Mineral ... but not
  Banking & Finance). PDFs the PDF maker only puts inside a combined PDF (Economy, Finance, LPG by default) are offered as their own PDFs too.
  The list also remembers PDFs from the last few days, so you can set a group up when today has no clips yet. JPG / ZIP groups still have
  a "whole folder" tick.

v3.0.27 - Send by mail: files per group are chosen by PDF NAME (PDF maker names), not by folder.
  * Group editor: tick PDFs from one flat list (search box). "Everything not taken by another group" = catch-all.
  * Defaults: Pride Group = Pride Group PDF only; United Group = United Group + Banking & Finance + Power, Energy & Mineral PDFs;
    Beximco group = everything else. New categories land in Beximco automatically.
  * Mail settings > "Restore default groups" loads these rules and keeps receivers of same-named groups.

v3.0.28 - Riko replaced by "Sajeeb" (placeholder character).
  * New skin nab_ui\mascot\sajeeb: one placeholder image per pose + multi-frame sets (walk 3, run 3, dance 2, celebrate 2, sleep 2).
    Replace the files with your own (same names, .webp). See README.txt in that folder. Frame lists are in mascot\skins.json.
  * Name tag always shown under him (Settings > Sajeeb > name, can be switched off). Desktop pet shows it too.
  * The old fox skins stay in the folder but are hidden. Chat lines that said Riko/fox/tail were changed.

v3.0.29 - Send by mail reads the real PDFs in <day>\OutputPDF (it no longer makes any PDF itself).
  * Pride = Pride Group PDF; United = Banking & Finance + Power, Energy & Mineral + every PDF made from the United Group folder;
    Beximco = every PDF not taken by another group. Telecom = Telecom folder zip. Edotco industry is switched OFF by default (send by hand).
    BAT / Xiaomi / ASK = all JPGs of their folder. "Restore default groups" in Mail settings loads these (receivers are kept).
  * Smart checks from earlier sends: usual file missing today, new file, far fewer/smaller than usual, receivers changed. Shown as "check" in the list and in the confirm box.
  * Character files are now editable in Documents\NAB Mascot (placeholders copied there on first run, never overwritten). Settings > Sajeeb > Open character folder.

v3.0.30 - Real Sajeeb character from your two sprite sheets + fix for the Telegram "Streak broken" spam.
  * Streak message was sent every minute (no once-per-day guard). Now once per day, remembered on disk (nab_streak_day.txt).
  * Sajeeb: 65 frames cut out of the sheets, upscaled 3x. walk 7 / run 7 (steps follow the distance walked, so feet do not slide),
    jump 7 (frame picked by speed up / down + landing), climb 4, dance 7, celebrate 4, wave 2, phone 2, sleep 2 (breathing),
    plus poses: laptop, umbrella, tea, cat hug, angry, sad, love, shy, thinking, peek and more. Idle poses are picked at random.
  * Settings > Sajeeb > Character: Sajeeb or Riko (the fox, with her outfits). Name tag follows whichever is chosen.
  * Pictures live in Documents\NAB Mascot\sajeeb. A new picture set backs up the old folder to backup_<date> first.

v3.0.31 - Sajeeb walk / run / climb fixed: the pictures face left (he was walking backwards). Walk, run and climb are now single pictures with Riko-style bobbing; climbing uses the back view.

v3.0.32 - Faster start and close, size auto-fill, desktop pet removed.
  * Start: the window opens at once with a skeleton screen; the engine, tools and local server load behind it (nab_main.py).
    The page shows its own skeleton until the first data arrives. Status text changes if loading takes long.
  * Close: windows vanish immediately, shutdown has a 4 s limit; the end-of-day tracker check shows "Closing NAB..." at once and gives up after 8 s.
  * Overlay: hide/show is a native Win32 call (cannot fail or hang) and the toggle looks at the real window state.
  * Position a-b fills the first Size field with b-a+1 columns (1-3 = 3, 2-6 = 5, 4-8 = 5); cursor goes straight to the height.
  * The desktop pet (Sajeeb outside the NAB window) is removed.
  * BUILD.bat leaves out unused big libraries (smaller EXE = faster unpack).

v3.0.33
- Startup: optional native splash (splash.png + BUILD.bat --splash) shows instantly while the one-file exe unpacks; closes when the NAB window is up. If it still feels slow, build --onedir (needs updater change).
- Auth screen: "Open Telegram group / bot chat" button.
- Sajeeb: new meme, quote, phone/tea/umbrella/laptop activities (English + Bangla). Settings > Memes, quotes and fun activities. Ctrl+K: "Sajeeb: ...".

v3.0.33 (launcher)
- NAB_Launcher.exe (source: NABLauncher.cs, built by BUILD.bat with the C# compiler that ships with Windows). Shows an animated splash instantly, starts NAB.exe, and closes the splash when NAB signals its window is up (named event Local\NAB_Splash_Ready). Put your desktop/taskbar shortcut on NAB_Launcher.exe. Keep it in the same folder as NAB.exe.
- Auto-update still replaces NAB.exe only; after an update, nab_updater.exe reopens via the launcher if present.
- The login screen has an "Open Telegram group" button (invite link in nab_telegram.TG_GROUP_LINK, or registry TGGroupLink).

v3.0.34 - one-folder build, installer and folder updater
- BUILD.bat now builds a ONE-FOLDER app (pyinstaller --onedir): build_output\NAB\ holds NAB.exe, NAB_Launcher.exe, nab_updater.exe and _internal\. No unpacking at every start.
- NAB_Setup.exe (Inno Setup, per-user install into %LOCALAPPDATA%\Programs\NAB, no admin needed). BUILD.bat runs it when Inno Setup 6 is installed (NAB_Setup.iss).
- NAB_win.zip is the auto-update package: a running NAB downloads it from the GitHub release, unpacks it to <install>\_update, closes, and nab_updater.exe (a temp copy) swaps the files, keeping the old version in _old for rollback, then reopens via NAB_Launcher.exe.
- Release assets to upload each time: NAB_win.zip and NAB_Setup.exe. Old one-file copies (v3.0.33 and older) cannot auto-update into this layout: install once with NAB_Setup.exe.
- Login: removed the Telegram link buttons and emoji icons from the lock screen. Request buttons: group has Allow / 2 Hours / Remember today / Deny; owner has Allow / 2 Hours / Remember today / Remember for days / Deny (days in Settings > Sign-in, default 7).
- Window title bar now follows the theme colour (DwmSetWindowAttribute; exact colour on Windows 11, dark/light on Windows 10). API: titlebar.
- Launcher splash uses the real transparent PNG (per-pixel alpha) with a soft dark shadow behind it for legibility, an animated spinner and Sajeeb dancing (splash_mascot.png strip, built from dance_1..7).
- Window is framed again (the frameless try showed no window buttons on the test PC). The native title bar switches black (dark themes) / white (light themes) through DWM; the window handle is taken from the real window (sh.main.native) and failures are written to the log.
- Light themes now show the transparency chessboard on the canvas.
- Tracker: "Open sheet" and "Sync from sheet" buttons. The tracker now READS the Google Sheet (current + previous 2 months) when it opens (at most every 2 min) and on the Sync button: days missing here, or marked "not submitted" here, are filled from the sheet; papers found only in the sheet are added to the list. A day already submitted on this PC is never overwritten (counted as "differ").
- Sheet writes now find each paper's row by NAME (column B) instead of list position, and append new papers at the bottom.
- Tracker sync fix: only real newspaper rows are read (stops at the first total / note / blank / numeric row under the list; names must contain letters and must not start with Total, Extra, Grand ...). Every sync rebuilds the days it pulled earlier and removes junk names (numbers, "Total = ...") that an earlier sync added to the paper list.

v3.0.40
- Start-up is one flow: dark launcher screen, then the intro built from the real NAB layout and colours, then the app (no old splash, no blank gap).
- Papers: add/rename/remove/reorder save instantly; the papers file is backed up (.bak and daily copies) and never replaced by defaults. Paper menu has "Add or edit papers".
- Metadata overlay jumps to the size height field like the main app.
- WhatsApp: Settings > WhatsApp; pictures are sent as files (original quality) by default; the link is kept in the saved profile; sending tries several send-button selectors and Enter. Untested against the live WhatsApp Web.
- Sync: only the OWNER PC uploads (made owner once with Telegram approval). Every other PC downloads automatically, including a fresh install. Optional Settings ID gives each person their own settings set.

v3.0.41
- Start-up is light: no spinner, no continuous animation, ~3 s, fewer plates, only transform/opacity (gentle on weak GPUs). Launcher is a still dark screen.
- NAB opens as a normal maximised window (never borderless full screen). F11 still toggles full screen.
- Date button: new in-app calendar (the browser date picker did not open).

v3.0.42
- Update screen: animated progress while unpacking, and the app now really quits so the updater can finish (before, it could hang on "Launching updater").
- Overlay: Ctrl+Z within 20 s undoes the last save and puts the metadata back for fixing.
- Page field: a single digit becomes two (7 -> 07).
- Ctrl+K (app and overlay): category search. Tab/arrows move, Enter selects, Alt+Enter adds to a batch and lets you pick another.
- New intro: glass shatters, arc reactor spins, lightning pulls the real UI panels into place, sparks on landing.
- WhatsApp: reopens and retries once if the browser closes during a send; normal browser identity.

v3.0.43
- Fixed the Telegram /restart loop: the command is now marked as read before restarting, and commands sent while NAB was closed are ignored at start.

v3.0.44
- Category search moved to Ctrl + numpad plus. Ctrl+K is the command bar again.
- Telegram sends wait and retry when Telegram's flood limit (429) is hit.

v3.0.45
- Updater safety net: if a new version never starts, the old files are put back (the update is still required; nothing lets a PC stay on an old version).
- The previous run's log is kept (nab_log.prev.txt) so a crash can be read. Telegram: /health and /log.
- Style polish: focus rings, depth, hover/press feedback, thin scrollbars, tidier settings headings. Reduced-motion respected.

v3.0.46 - Accounts, WhatsApp queue, self-check
 * Accounts (Settings > Accounts): named logins with owner / staff / viewer roles, activity log, password reset, lockout after wrong passwords. Made on the owner PC, downloaded by every other PC. Telegram approval still works.
 * WhatsApp: double-click-safe Retry, send queue with Sent/Failed status, link health, repeat-send guard, all sending options in Settings, browser restarts cleanly if it closes mid-send.
 * Self-check (Settings > Self-check): clock, internet, update server, Drive, Telegram, WhatsApp, disk, tools, backups, accounts.
 * Backups now include accounts and WhatsApp settings (30 kept).
 * The Google key is no longer in the repository; the build writes it from the GDRIVE_KEY_JSON secret. Automatic tests run before every build.

v3.0.47 - Stage 2: archive and search
 * New clip archive (SQLite, Documents\nab_archive.db): every saved clip with paper, page, position, size, date, category and who saved it. Built from file names and folders, no OCR needed. Old OCR text is taken over automatically.
 * Search screen: words plus filters (paper, category, page, saved by, date range), saved searches as one-click buttons, export to Excel or CSV (Documents\NAB Exports), copy results.
 * Find duplicates: groups of look-alike clips with Open and Delete.
 * Save-time warning: if a new clip looks like one already saved, a warning shows which one (nothing is blocked).
 * Batch mode (Ctrl+K, Batch: open a folder of images): opens a folder of page images one by one, the next opens after each save.

v3.0.48 - Phone queue: clips typed on the phone app (NAB Metadata) wait in a new Phone screen; Use fills paper, page, position, size and category. Epaper address for each paper. Report builder (stage 3 part).
