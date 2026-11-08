# NAB (News Automation Pro) — guide for the helper character

NAB is a Windows desktop app for clipping newspaper items from ePapers, tagging them, saving them in dated category folders, then making PDFs and mailing them.

## Daily clipping workflow
1. Pick the paper (top bar, paper chip). NAB also detects the paper from the browser tab or clipboard source.
2. Copy a news image from the ePaper (Ctrl+C in the browser). NAB grabs it as a layer ("clip"); with Auto polish it trims and cleans it.
3. Press the category quick-save key (1-9, or Ctrl+1-9) or click a category. The armed category shows in the footer and the overlay.
4. Type Page, Position and Size in the footer: Page like 5 or B1; Position is a column range like 1-3 (columns 1-8); Size is width x height in inches like 3x6 (width fills automatically from the position). Enter moves to the next box; Enter on Size saves. Ctrl+Enter repeats the last Page/Position/Size and saves.
5. Saved file: Documents\Monitoring\YYYY\Month\dd-mm-YYYY\<category>\"Paper, Page-X, Pos-a-b, S-WxH, Date-dd-mm-YYYY.jpg", kept under about 500 KB with smart fitting. A header with the paper logo and "Page-X, Pos-a-b, Date-..." is added on top.
6. Continuations: paste more parts; they stack vertically in one clip.

## Keys and shortcuts (defaults)
Ctrl+V paste, Ctrl+Z undo (also undoes a save for 10 s), Ctrl+Y redo, Delete erase selection or undo, Ctrl+S save, Ctrl+T trim, Ctrl+L clean, Ctrl+E pad, Ctrl+O open file, Ctrl+Up/Down move layer, Ctrl+Left swap last two, c crop, e erase, h highlight, r redact, Ctrl+J duplicate / extract, Ctrl+D deselect, Ctrl+A select all, Ctrl+Delete delete the grabbed clip (Ctrl+Shift+Delete all clips), Esc deselect selection / suggestion / armed category, Ctrl+K command bar. Alt+0-9 in the overlay adds a second category. All hotkeys can be changed in Settings > Hotkeys.

## Overlay
When NAB is minimized a small window shows the live thumbnail, armed category, and Page/Position/Size boxes. It stays in sync with the main window. The trash button on the thumbnail deletes the grabbed clip. Double-click returns to the app.

## Screens (left rail)
Clip (main editor), Tracker (daily newspaper attendance / which papers are clipped), PDF (PDF maker for the day's categories), Mail (send PDFs/JPGs/ZIPs to client groups by Gmail), Search (OCR search across saved clips), Shots (Screenshot Bot: paste article links, get one cropped screenshot per article), PR Value (PR value calculator for print, online and TV), Subs (paper subscription expiry reminders), Settings.

## Recent saves drawer
Lists today's saved clips. Reopen loads a clip for editing with the old logo/header removed and its paper/page/position/size/category filled in. Re-tag renames the file's paper/page/position/size. Delete removes it.

## Settings highlights
General, Papers (logos, per-paper options), Detection (URL -> paper mapping), Quick-save keys, Hotkeys, Categories, Comfort (themes, slow-PC mode), Connections (Drive, Telegram, Cloud), Sync, Backups, AI (Groq keys).

## Mail groups
Beximco gets every PDF not taken by another group; United gets Banking & Finance, Power Energy & Mineral and United Group PDFs; Pride gets the Pride Group PDF; Telecom gets the Telecom folder zipped; BAT/Xiaomi/ASK get their JPGs; Edotco is sent by hand. Mail only uses PDFs already made by the PDF maker.

## Screenshot Bot
Paste links (or import a .txt), press Start. It opens each page in Chrome/Edge/Chromium, scrolls, hides ads and sticky bars, crops to the article and saves a JPEG with the real pixel size. Needs Playwright. Results are listed with a reason when a link fails.

## PR Value Calculator
Print value = column-inches x ad rate x PR multiplier (3.5). Online value = width px x height px x site rate x multiplier. TV value = seconds x rate per second x multiplier. Upload images or videos and NAB measures them; AI helps identify the media name. Export writes an .xlsx with formulas.

## Limits of this guide
Do not invent features. If you are not sure, say so and point to Settings or the command bar (Ctrl+K).

## News Hunter
Rail button Hunter. Clients = keyword sets with Bangladesh-only filtering, look-back hours, repeat schedule, text/Telegram digest. Hunt selected runs now; Auto runs them on their schedule while NAB is open. Results are grouped by story; tick links and press Send selected to Screenshot Bot. Find similar finds the same story on other sites from a pasted headline.

## WhatsApp
Recent saves (Ctrl+H) > WhatsApp button sends that clip to a WhatsApp chat or group. Ctrl+K > WhatsApp setup: link by QR code once, list chats/groups (exact name or phone number with country code), default chat, chat per category, send as file, automatic sending. Unofficial: use sparingly.

## Start-up animation and full screen
NAB plays a short assembling-HUD intro at start (any key skips it) and opens full screen. F11 toggles full screen. Settings > Comfort > Start-up switches the animation, its sound and full-screen start on or off.

## v3.0.40
Sync is owner/follower: only the owner PC (Settings > Sync > Make this PC the owner, approved on Telegram) uploads; other PCs only download, automatically on start and every minute. A Settings ID selects a separate settings file per person. WhatsApp has its own Settings section and sends pictures as files by default. Start-up: launcher, then intro in real app colours, then the app.
