NAB Tab Reporter (optional, makes paper detection use the real page URL)

Chrome / Edge / Brave / Opera / Vivaldi
 1. Open the extensions page (chrome://extensions, edge://extensions, brave://extensions, opera://extensions, vivaldi://extensions)
 2. Turn on Developer mode -> "Load unpacked" -> choose this NAB_TabReporter folder.

Firefox (121 or newer)
 1. Open about:debugging#/runtime/this-firefox -> "Load Temporary Add-on..."
 2. Choose the file manifest.json inside the folder "extension_firefox" that NAB prepares (Settings -> About -> Setup guide -> Firefox).
    Firefox forgets a temporary add-on when it closes; for a permanent install use Firefox Developer Edition / ESR with
    xpinstall.signatures.required = false, or sign the add-on for yourself (free "unlisted" signing at addons.mozilla.org).

Keep NAB running; no other setup. Without it NAB tries to read the address bar itself if `pip install uiautomation` is present.
