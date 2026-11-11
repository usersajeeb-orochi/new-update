# nab_headless_ops.py — Telegram reports, Drive upload and archive scans.
#
# These methods are lifted UNCHANGED from the old NewsClipper class (they never
# touched a widget, only attributes the new engine also has), so Telegram
# commands and Drive uploads behave exactly as before.  Generated once from
# nab_app.py; edit freely.
import os
import re
import time
import logging
import threading
import datetime

from PIL import Image

from nab_telegram import _tg_send, _tg_send_photo, _tg_send_document, PC_NAME
import nab_connections

C_SUCCESS = "#10B981"


def _TA():
    """TelegramAuth, imported on first use (nab_auth is the heavy module)."""
    import nab_auth
    return nab_auth.TelegramAuth


class HeadlessOps:
    _DATE_PATTERN = re.compile(r"^\d{2}-\d{2}-\d{4}$")  # DD-MM-YYYY

    def _set_daily_goal(self, goal):
        self.daily_goal = goal
        self.daily_goal_notified = False
        today_count = sum(1 for h in self.session_history
                          if h.get("time", "").split(":")[0].isdigit())
        _tg_send(f"🎯 Daily goal set to <b>{goal} clips</b> on {PC_NAME}.\nCurrent count: {today_count}.")

    def _send_pcs_info(self):
        elapsed = int(time.time() - _TA()._session_start) if _TA()._session_start else 0
        hrs, rem = divmod(elapsed, 3600)
        mins = rem // 60
        saves = len(self.session_history)
        _tg_send(
            f"🖥 <b>Active PC Info</b>\n\n"
            f"💻 PC: <code>{PC_NAME}</code>\n"
            f"🕐 Session: {hrs}h {mins}m\n"
            f"💾 Saves: {saves}\n"
            f"📰 Current paper: {self.paper_combo.get()}"
        )

    def _send_tg_report(self):
        from collections import Counter
        saves = len(self.session_history)
        cats = Counter(h.get("category", "?") for h in self.session_history)
        papers = Counter(
            os.path.basename(h.get("path", "")).split(",")[0]
            for h in self.session_history
        )
        elapsed = int(time.time() - _TA()._session_start) if _TA()._session_start else 0
        hrs, rem = divmod(elapsed, 3600)
        mins = rem // 60
        deadline_str = (
            datetime.datetime.fromtimestamp(_TA()._access_deadline).strftime("%H:%M:%S")
            if _TA()._access_deadline else "Unlimited"
        )
        cat_lines = "\n".join(f"  • {c}: {n}" for c, n in cats.most_common(5)) or "  None"
        paper_lines = "\n".join(f"  • {p}: {n}" for p, n in papers.most_common(5)) or "  None"
        goal_line = ""
        if self.daily_goal > 0:
            pct = min(100, int(saves / self.daily_goal * 100))
            goal_line = f"\n🎯 Goal: {saves}/{self.daily_goal} ({pct}%)"
        _tg_send(
            f"📊 <b>NAB Activity Report</b>\n"
            f"💻 PC: <code>{PC_NAME}</code>\n"
            f"🕐 Session: {hrs}h {mins}m\n"
            f"⏱ Expires: {deadline_str}\n"
            f"💾 Total saves: <b>{saves}</b>{goal_line}\n\n"
            f"📁 By category:\n{cat_lines}\n\n"
            f"📰 By newspaper:\n{paper_lines}"
        )

    def _send_tg_status(self):
        elapsed = int(time.time() - _TA()._session_start) if _TA()._session_start else 0
        hrs, rem = divmod(elapsed, 3600)
        mins = rem // 60
        deadline_str = (
            datetime.datetime.fromtimestamp(_TA()._access_deadline).strftime("%H:%M:%S")
            if _TA()._access_deadline else "Unlimited"
        )
        _tg_send(
            f"🟢 NAB running on <b>{PC_NAME}</b>\n"
            f"🕐 Session: {hrs}h {mins}m\n"
            f"⏱ Access expires: {deadline_str}\n"
            f"📰 Paper: {self.paper_combo.get()}\n"
            f"📅 Date: {self.current_date.strftime('%d-%m-%Y')}"
        )

    def _send_last_file(self):
        if not self.session_history:
            _tg_send(f"📭 No files saved this session on {PC_NAME}.")
            return
        last = self.session_history[-1]
        path = last.get("path", "")
        if os.path.exists(path):
            try:
                import io
                img = Image.open(path)
                img.thumbnail((800, 1200))
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=80)
                _tg_send_photo(buf.getvalue(), f"Last file — {os.path.basename(path)}\n{last.get('category','?')} — {last.get('time','?')}")
            except Exception as e:
                _tg_send(f"❌ Could not send file: {e}")
        else:
            _tg_send(f"❌ File not found: {path}")

    def _send_files_today(self):
        today = self.current_date.strftime("%Y-%m-%d")
        today_files = [h for h in self.session_history if today in h.get("path", "") or today in h.get("time", "")]
        if not today_files:
            _tg_send(f"📭 No files saved today on {PC_NAME}.")
            return
        lines = [f"• [{h['time']}] {h['category']} → {os.path.basename(h['path'])}" for h in today_files[-20:]]
        _tg_send(f"📁 <b>Today's saves on {PC_NAME} ({len(today_files)} total):</b>\n\n" + "\n".join(lines))

    def _delete_last_file(self):
        if not self.session_history:
            _tg_send(f"📭 No files to delete on {PC_NAME}.")
            return
        last = self.session_history[-1]
        path = last.get("path", "")
        try:
            if os.path.exists(path):
                os.remove(path)
                self.session_history.pop()
                _tg_send(f"🗑️ Deleted: <code>{os.path.basename(path)}</code> on {PC_NAME}.")
            else:
                _tg_send(f"❌ File not found on {PC_NAME}.")
        except Exception as e:
            _tg_send(f"❌ Delete failed: {e}")

    def _send_last_n_files(self, n):
        recent = self.session_history[-n:]
        if not recent:
            _tg_send(f"📭 No files available on {PC_NAME}.")
            return
        sent = 0
        for h in recent:
            path = h.get("path", "")
            if os.path.exists(path):
                try:
                    import io
                    img = Image.open(path)
                    img.thumbnail((800, 1200))
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=75)
                    _tg_send_document(buf.getvalue(), os.path.basename(path),
                                      f"{h.get('category','?')} — {h.get('time','?')}")
                    sent += 1
                    time.sleep(0.5)
                except Exception:
                    pass
        _tg_send(f"✅ Sent {sent}/{len(recent)} files from {PC_NAME}.")

    def _scan_category_files_on_disk(self, cat_query, date_filter=None):
        """
        Scan base_root on disk for files matching a category name and optional date.
        Folder structure: base_root/YYYY/Month/DD-MM-YYYY/Category[/SubCategory]/files
        date_filter: string like '02-02-2023' (DD-MM-YYYY) or None for all dates.
        Returns list of (full_path, category_path, date_str).
        """
        results = []
        if not os.path.exists(self.base_root):
            return results
        try:
            for year_d in os.scandir(self.base_root):
                if not year_d.is_dir(): continue
                for month_d in os.scandir(year_d.path):
                    if not month_d.is_dir(): continue
                    for date_d in os.scandir(month_d.path):
                        if not date_d.is_dir(): continue
                        date_str = date_d.name  # e.g. "02-02-2023"
                        # If date filter provided, skip non-matching dates
                        if date_filter and date_filter != date_str:
                            continue
                        # Walk all subdirs under this date folder
                        for root, dirs, files in os.walk(date_d.path):
                            rel = os.path.relpath(root, date_d.path)
                            # rel is like "Category" or "Category/SubCategory" or "."
                            cat_path = rel if rel != "." else ""
                            if cat_query.lower() in cat_path.lower() or cat_query.lower() in root.lower():
                                for f in files:
                                    if f.lower().endswith((".jpg", ".jpeg", ".png")):
                                        results.append((os.path.join(root, f), cat_path or date_str, date_str))
        except Exception as e:
            logging.error(f"_scan_category_files_on_disk: {e}")
        results.sort(key=lambda x: x[2])
        return results

    def _list_all_categories_on_disk(self):
        """Return a set of all category paths found on disk."""
        cats = set()
        if not os.path.exists(self.base_root):
            return cats
        try:
            for year_d in os.scandir(self.base_root):
                if not year_d.is_dir(): continue
                for month_d in os.scandir(year_d.path):
                    if not month_d.is_dir(): continue
                    for date_d in os.scandir(month_d.path):
                        if not date_d.is_dir(): continue
                        for root, dirs, files in os.walk(date_d.path):
                            has_imgs = any(f.lower().endswith((".jpg",".jpeg",".png")) for f in files)
                            if has_imgs:
                                rel = os.path.relpath(root, date_d.path)
                                cats.add(rel if rel != "." else "(root)")
        except Exception as e:
            logging.error(f"_list_all_categories_on_disk: {e}")
        return cats

    def _send_category_files(self, raw_arg):
        """
        Handles: /send CategoryName [DD-MM-YYYY]
        Scans disk so it works across sessions and after restarts.
        """
        import io as _io

        # Parse optional date at end: /send Economy 02-02-2023
        date_filter = None
        cat = raw_arg.strip()
        parts = cat.rsplit(" ", 1)
        if len(parts) == 2:
            maybe_date = parts[1].strip()
            import re as _re
            if _re.match(r"^\d{2}-\d{2}-\d{4}$", maybe_date):
                date_filter = maybe_date
                cat = parts[0].strip()

        _tg_send(
            f"🔍 Searching for <b>{cat}</b>"
            + (f" on <b>{date_filter}</b>" if date_filter else " (all dates)")
            + f" on <b>{PC_NAME}</b>..."
        )

        # First try disk scan
        found = self._scan_category_files_on_disk(cat, date_filter)

        # Also merge any in-memory session history matches (current session)
        session_paths = set(h.get("path", "") for h in self.session_history
                            if cat.lower() in h.get("category", "").lower())
        if date_filter:
            session_paths = {p for p in session_paths if date_filter in p}
        # Add session files not already in disk results
        disk_paths = {r[0] for r in found}
        for sp in sorted(session_paths):
            if sp not in disk_paths and os.path.exists(sp):
                rel = os.path.relpath(os.path.dirname(sp), self.base_root)
                found.append((sp, rel, date_filter or "session"))

        if not found:
            # Suggest similar categories
            all_cats = self._list_all_categories_on_disk()
            similar = [c for c in all_cats if any(w in c.lower() for w in cat.lower().split())]
            tip = ""
            if similar:
                tip = "\n\n💡 Similar categories found:\n" + "\n".join(f"  • {c}" for c in sorted(similar)[:8])
            _tg_send(
                f"📭 No files found for category <b>'{cat}'</b>"
                + (f" on date <b>{date_filter}</b>" if date_filter else "")
                + f" on <b>{PC_NAME}</b>.{tip}"
                + "\n\nSend /categories to see all available categories."
            )
            return

        # Group by date for summary
        by_date = {}
        for path, cat_path, date_str in found:
            by_date.setdefault(date_str, []).append((path, cat_path))

        summary_lines = []
        total = len(found)
        for ds, files in sorted(by_date.items()):
            summary_lines.append(f"📅 <b>{ds}</b>: {len(files)} file(s)")

        _tg_send(
            f"📁 <b>Found {total} file(s) for '{cat}' on {PC_NAME}</b>\n\n"
            + "\n".join(summary_lines)
            + "\n\nSending now..."
        )

        sent = 0
        limit = 20  # max files to send in one command
        for path, cat_path, date_str in found[:limit]:
            if os.path.exists(path):
                try:
                    img = Image.open(path)
                    img.thumbnail((900, 1400))
                    buf = _io.BytesIO()
                    img.save(buf, format="JPEG", quality=80)
                    caption = f"📂 {cat_path}\n📅 {date_str}\n📄 {os.path.basename(path)}"
                    _tg_send_document(buf.getvalue(), os.path.basename(path), caption)
                    sent += 1
                    time.sleep(0.4)
                except Exception as ex:
                    logging.error(f"_send_category_files send: {ex}")

        if total > limit:
            _tg_send(
                f"✅ Sent {sent}/{total} files from <b>'{cat}'</b> on {PC_NAME}.\n"
                f"⚠️ Only first {limit} shown. Use a date filter to narrow down:\n"
                f"<code>/send {cat} DD-MM-YYYY</code>"
            )
        else:
            _tg_send(f"✅ Sent {sent}/{total} files from <b>'{cat}'</b> on {PC_NAME}.")

    def _send_categories_list(self, chat_id=None):
        """Send a list of all categories found on disk."""
        cats = self._list_all_categories_on_disk()
        if not cats:
            _tg_send(f"📭 No categories found on disk for <b>{PC_NAME}</b>.\nBase folder: <code>{self.base_root}</code>", chat_id=chat_id)
            return
        sorted_cats = sorted(cats)
        lines = [f"  • {c}" for c in sorted_cats[:50]]
        suffix = f"\n...and {len(sorted_cats)-50} more." if len(sorted_cats) > 50 else ""
        _tg_send(
            f"📂 <b>Categories on {PC_NAME}</b> ({len(sorted_cats)} total):\n\n"
            + "\n".join(lines) + suffix
            + "\n\n<i>Use: /send CategoryName [DD-MM-YYYY]</i>",
            chat_id=chat_id
        )

    def _send_category_files_to(self, raw_arg, chat_id):
        """Like _send_category_files but sends to a specific chat_id (for group support)."""
        import io as _io
        import re as _re

        date_filter = None
        cat = raw_arg.strip()
        parts = cat.rsplit(" ", 1)
        if len(parts) == 2:
            maybe_date = parts[1].strip()
            if _re.match(r"^\d{2}-\d{2}-\d{4}$", maybe_date):
                date_filter = maybe_date
                cat = parts[0].strip()

        found = self._scan_category_files_on_disk(cat, date_filter)
        # Also add session files
        for h in self.session_history:
            if cat.lower() in h.get("category", "").lower():
                sp = h.get("path", "")
                if date_filter and date_filter not in sp:
                    continue
                if sp not in {r[0] for r in found} and os.path.exists(sp):
                    found.append((sp, h.get("category", ""), date_filter or "session"))

        if not found:
            all_cats = self._list_all_categories_on_disk()
            similar = [c for c in all_cats if any(w in c.lower() for w in cat.lower().split())]
            tip = ("\n💡 Similar: " + ", ".join(sorted(similar)[:5])) if similar else ""
            _tg_send(f"📭 No files found for <b>'{cat}'</b>" + (f" on {date_filter}" if date_filter else "") + f".{tip}", chat_id=chat_id)
            return

        by_date = {}
        for path, cat_path, date_str in found:
            by_date.setdefault(date_str, []).append((path, cat_path))
        summary = "\n".join(f"📅 <b>{ds}</b>: {len(fs)} file(s)" for ds, fs in sorted(by_date.items()))
        _tg_send(f"📁 <b>{len(found)} file(s) for '{cat}'</b>\n{summary}\nSending...", chat_id=chat_id)

        sent = 0
        for path, cat_path, date_str in found[:20]:
            if os.path.exists(path):
                try:
                    img = Image.open(path)
                    img.thumbnail((900, 1400))
                    buf = _io.BytesIO()
                    img.save(buf, format="JPEG", quality=80)
                    caption = f"📂 {cat_path}\n📅 {date_str}\n📄 {os.path.basename(path)}"
                    _tg_send_document(buf.getvalue(), os.path.basename(path), caption, chat_id=chat_id)
                    sent += 1
                    time.sleep(0.4)
                except Exception as ex:
                    logging.error(f"_send_category_files_to: {ex}")
        _tg_send(f"✅ Sent {sent}/{len(found)} files.", chat_id=chat_id)

    def _send_stats(self):
        from collections import Counter
        if not self.session_history:
            _tg_send(f"📊 No stats yet on {PC_NAME}.")
            return
        papers = Counter(os.path.basename(h.get("path", "")).split(",")[0] for h in self.session_history)
        cats = Counter(h.get("category", "?") for h in self.session_history)
        paper_lines = "\n".join(f"  {i+1}. {p}: {n}" for i, (p, n) in enumerate(papers.most_common(8)))
        cat_lines = "\n".join(f"  {i+1}. {c}: {n}" for i, (c, n) in enumerate(cats.most_common(8)))
        _tg_send(
            f"📈 <b>NAB Stats — {PC_NAME}</b>\n\n"
            f"<b>Top Newspapers:</b>\n{paper_lines}\n\n"
            f"<b>Top Categories:</b>\n{cat_lines}\n\n"
            f"Total clips this session: <b>{len(self.session_history)}</b>"
        )

    def _scan_all_files(self, date_filter=None):
        """
        Recursively scan base_root for all saved files.
        Returns list of (date_str, category, file_path, file_name)

        date_filter: None = all, or a set of 'DD-MM-YYYY' strings
        Uses a recursive walk — works with ANY folder structure depth.
        """
        results = []
        base    = self.base_root
        if not base or not os.path.exists(base):
            return results

        def _walk(path, found_date=None, found_cat=None):
            try:
                entries = list(os.scandir(path))
            except PermissionError:
                return

            for entry in entries:
                if entry.name.startswith(".") or entry.name.startswith("__"):
                    continue

                if entry.is_file():
                    # Only collect if we have both date and category context
                    if found_date and found_cat:
                        if date_filter is None or found_date in date_filter:
                            results.append((found_date, found_cat, entry.path, entry.name))
                    continue

                if not entry.is_dir():
                    continue

                name = entry.name

                # Is this a date folder? DD-MM-YYYY
                if self._DATE_PATTERN.match(name):
                    _walk(entry.path, found_date=name, found_cat=None)

                # Already have a date — this must be a category folder
                elif found_date and not found_cat:
                    _walk(entry.path, found_date=found_date, found_cat=name)

                # Already have both — could be a subcategory, keep category as top-level
                elif found_date and found_cat:
                    _walk(entry.path, found_date=found_date, found_cat=found_cat)

                # No date yet — keep walking (year, month, custom folder, any depth)
                else:
                    _walk(entry.path, found_date=None, found_cat=None)

        _walk(base)
        return results

    def _get_gdrive_service(self):
        """Get Google Drive service using service account credentials."""
        try:
            from googleapiclient.discovery import build
            creds = nab_connections.drive_credentials()
            if not creds:
                logging.error("Google key not found (not bundled in this build).")
                return None
            return build("drive", "v3", credentials=creds, cache_discovery=False)
        except Exception as e:
            logging.error(f"_get_gdrive_service: {e}")
            return None

    def _drive_get_or_create_folder(self, service, parent_id, name):
        """Get or create a folder in Google Drive — supports both personal and Shared Drive."""
        if not parent_id:
            return None
        try:
            safe_name = name.replace("\\", "\\\\").replace("'", "\\'")
            q         = f"name='{safe_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            result    = service.files().list(
                q=q, fields="files(id,name)", pageSize=1,
                supportsAllDrives=True, includeItemsFromAllDrives=True
            ).execute()
            files = result.get("files", [])
            if files:
                return files[0]["id"]
            meta = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
            f    = service.files().create(body=meta, fields="id", supportsAllDrives=True).execute()
            return f["id"]
        except Exception as e:
            logging.error(f"_drive_get_or_create_folder '{name}': {e}")
            return None

    def _drive_file_exists(self, service, parent_id, filename):
        """Check if a file already exists in a Drive folder."""
        if not parent_id:
            return False
        try:
            safe_name = filename.replace("\\", "\\\\").replace("'", "\\'")
            q         = f"name='{safe_name}' and '{parent_id}' in parents and trashed=false"
            result    = service.files().list(
                q=q, fields="files(id)", pageSize=1,
                supportsAllDrives=True, includeItemsFromAllDrives=True
            ).execute()
            return len(result.get("files", [])) > 0
        except Exception as e:
            logging.error(f"_drive_file_exists '{filename}': {e}")
            return False

    def _drive_upload_file(self, service, parent_id, file_path, filename):
        """Upload a single file to Google Drive folder."""
        if not parent_id:
            raise ValueError(f"parent_id is None for {filename}")
        from googleapiclient.http import MediaFileUpload
        import mimetypes
        mime, _ = mimetypes.guess_type(file_path)
        mime     = mime or "image/jpeg"
        meta     = {"name": filename, "parents": [parent_id]}
        media    = MediaFileUpload(file_path, mimetype=mime, resumable=False)
        service.files().create(
            body=meta, media_body=media, fields="id",
            supportsAllDrives=True
        ).execute()
        return True

    def _test_drive_connection(self):
        """Test Drive connection and send diagnostic info via Telegram."""
        try:
            service = self._get_gdrive_service()
            root_id = self._drive_get_root_id()
            if not service:
                _tg_send(f"❌ Drive test on <b>{PC_NAME}</b>: No service (check creds file)")
                return
            if not root_id:
                _tg_send(f"❌ Drive test on <b>{PC_NAME}</b>: No root folder ID")
                return
            # Try to list files in root folder
            result = service.files().list(
                q=f"'{root_id}' in parents and trashed=false",
                fields="files(id,name)", pageSize=5
            ).execute()
            files = result.get("files", [])
            # Try to create a test folder
            meta   = {"name": "_NAB_TEST_", "mimeType": "application/vnd.google-apps.folder", "parents": [root_id]}
            folder = service.files().create(body=meta, fields="id,name").execute()
            # Delete it immediately
            service.files().delete(fileId=folder["id"]).execute()
            _tg_send(
                f"✅ <b>Drive connection OK — {PC_NAME}</b>\n\n"
                f"Root folder ID: <code>{root_id}</code>\n"
                f"Existing items in root: <b>{len(files)}</b>\n"
                f"Write access: ✅ confirmed\n\n"
                f"Drive is ready for uploads."
            )
        except Exception as e:
            _tg_send(
                f"❌ <b>Drive test FAILED — {PC_NAME}</b>\n\n"
                f"Error: <code>{e}</code>\n\n"
                f"Root ID: <code>{self._drive_get_root_id()}</code>"
            )

    def _drive_get_root_id(self):
        """Drive root folder ID — built in (override: Settings → Advanced)."""
        return nab_connections.drive_folder_id()

    def _upload_date_list(self, category, dates):
        """Upload all files for a list of specific dates. category='*' means all."""
        import threading
        threading.Thread(target=self._upload_date_list_thread, args=(category, dates), daemon=True).start()

    def _upload_date_list_thread(self, category, dates):
        try:
            service = self._get_gdrive_service()
            root_id = self._drive_get_root_id()
            if not service or not root_id:
                missing = []
                if not service: missing.append("Google key (not bundled in this build)")
                if not root_id: missing.append("Drive root folder ID")
                _tg_send(
                    f"❌ <b>Drive not configured on {PC_NAME}</b>\n\n"
                    f"Missing: {', '.join(missing)}\n\n"
                    f"Rebuild NAB with the Google key next to BUILD.bat (see Settings → Advanced)."
                )
                return

            base = self.base_root
            if not os.path.exists(base):
                _tg_send(f"❌ Base folder not found: <code>{base}</code>")
                return

            date_set  = set(dates)
            to_upload = self._scan_all_files(date_filter=date_set if date_set != {"all"} else None)
            if category != "*":
                to_upload = [(d, c, fp, fn) for d, c, fp, fn in to_upload if c == category]

            total     = len(to_upload)
            uploaded  = 0
            skipped   = 0

            if total == 0:
                _tg_send(f"📭 No files found on <b>{PC_NAME}</b> for the requested dates.")
                return

            cat_label = category if category != "*" else "all categories"
            _tg_send(
                f"📤 <b>Starting Upload — {PC_NAME}</b>\n"
                f"📁 {cat_label} | 📅 {len(dates)} date(s)\n"
                f"Files: <b>{total}</b>"
            )

            for date_str, cat, fpath, fname in to_upload:
                try:
                    year_id = self._drive_get_or_create_folder(service, root_id, date_str[:4] if len(date_str) > 6 else "Unknown")
                    date_id = self._drive_get_or_create_folder(service, year_id, date_str)
                    cat_id  = self._drive_get_or_create_folder(service, date_id, cat)
                    if self._drive_file_exists(service, cat_id, fname):
                        skipped += 1
                    else:
                        if self._drive_upload_file(service, cat_id, fpath, fname):
                            uploaded += 1
                        else:
                            skipped += 1
                except Exception as e:
                    logging.error(f"upload {fname}: {e}")
                    skipped += 1

            _tg_send(
                f"✅ <b>Upload Complete — {PC_NAME}</b>\n\n"
                f"📁 {cat_label}\n"
                f"📅 {len(dates)} date(s)\n"
                f"📤 Uploaded: <b>{uploaded}</b>\n"
                f"⏭ Skipped (already on Drive): <b>{skipped}</b>\n"
                f"📊 Total: <b>{total}</b>"
            )
        except Exception as e:
            logging.error(f"_upload_date_list_thread: {e}")
            _tg_send(f"❌ Upload error on <b>{PC_NAME}</b>: {e}")

    def _upload_old_files_thread(self, category, scope):
        try:
            service = self._get_gdrive_service()
            root_id = self._drive_get_root_id()
            if not service or not root_id:
                missing = []
                if not service: missing.append("Google key (not bundled in this build)")
                if not root_id: missing.append("Drive root folder ID")
                _tg_send(
                    f"❌ <b>Drive not configured on {PC_NAME}</b>\n\n"
                    f"Missing: {', '.join(missing)}\n\n"
                    f"Rebuild NAB with the Google key next to BUILD.bat (see Settings → Advanced)."
                )
                return

            base = self.base_root
            if not os.path.exists(base):
                _tg_send(f"❌ Base folder not found on <b>{PC_NAME}</b>: <code>{base}</code>")
                return

            # Use universal scanner — works with any folder structure/drive
            all_files = self._scan_all_files()
            if category != "*":
                all_files = [(d, c, fp, fn) for d, c, fp, fn in all_files if c == category]

            # Filter by scope
            to_upload = []
            for date_str, cat, fpath, fname in all_files:
                if scope.lower() == "all":
                    to_upload.append((date_str, cat, fpath, fname))
                    continue
                try:
                    dt = datetime.datetime.strptime(date_str, "%d-%m-%Y")
                    if len(scope) == 10 and scope.count("-") == 2:
                        if date_str == scope: to_upload.append((date_str, cat, fpath, fname))
                    elif len(scope) == 7:  # YYYY-MM
                        if dt.strftime("%Y-%m") == scope: to_upload.append((date_str, cat, fpath, fname))
                    elif len(scope) == 4:  # YYYY
                        if dt.strftime("%Y") == scope: to_upload.append((date_str, cat, fpath, fname))
                except Exception:
                    pass

            total    = len(to_upload)
            uploaded = 0
            skipped  = 0
            errors   = 0

            if total == 0:
                _tg_send(f"📭 No files found for <b>{category}</b> / <b>{scope}</b> on <b>{PC_NAME}</b>.")
                return

            _tg_send(f"📤 Starting upload on <b>{PC_NAME}</b>\nCategory: <b>{category}</b> | Scope: <b>{scope}</b>\nFiles: <b>{total}</b>")

            for date_str, cat, fpath, fname in to_upload:
                try:
                    try:
                        year = datetime.datetime.strptime(date_str, "%d-%m-%Y").strftime("%Y")
                    except Exception:
                        year = "Unknown"
                    year_id = self._drive_get_or_create_folder(service, root_id, year)
                    date_id = self._drive_get_or_create_folder(service, year_id, date_str)
                    cat_id  = self._drive_get_or_create_folder(service, date_id, cat)
                    if not cat_id:
                        errors += 1
                        continue
                    if self._drive_file_exists(service, cat_id, fname):
                        skipped += 1
                    else:
                        if self._drive_upload_file(service, cat_id, fpath, fname):
                            uploaded += 1
                        else:
                            errors += 1
                except Exception as e:
                    logging.error(f"upload file {fname}: {e}")
                    errors += 1

            _tg_send(
                f"✅ <b>Upload Complete — {PC_NAME}</b>\n\n"
                f"Category: <b>{category}</b> | Scope: <b>{scope}</b>\n"
                f"📤 Uploaded: <b>{uploaded}</b>\n"
                f"⏭ Skipped (already on Drive): <b>{skipped}</b>\n"
                f"❌ Errors: <b>{errors}</b>\n"
                f"📊 Total: <b>{total}</b>"
            )
        except Exception as e:
            logging.error(f"_upload_old_files_thread: {e}")
            _tg_send(f"❌ Upload error on <b>{PC_NAME}</b>: {e}")

    def _force_upload_category(self, category, date_str):
        """Force upload a specific category+date — triggered by cloud bot pending_req ping."""
        import threading
        threading.Thread(target=self._upload_old_files_thread, args=(category, date_str), daemon=True).start()

    def _scan_and_report_local(self):
        """Scan local disk and report what's available vs what's on Drive."""
        import threading
        threading.Thread(target=self._scan_and_report_local_thread, daemon=True).start()

    def _scan_and_report_local_thread(self):
        try:
            base = self.base_root
            if not os.path.exists(base):
                _tg_send(f"❌ Base folder not found on <b>{PC_NAME}</b>: <code>{base}</code>")
                return

            # Count files per category
            cat_counts = {}
            date_counts = {}
            total_files = 0

            all_files = self._scan_all_files()
            for date_str, cat, fpath, fname in all_files:
                cat_counts[cat]      = cat_counts.get(cat, 0) + 1
                date_counts[date_str] = date_counts.get(date_str, 0) + 1
                total_files          += 1

            if not cat_counts:
                _tg_send(f"📭 No files found on disk for <b>{PC_NAME}</b>.")
                return

            cat_lines  = "\n".join(f"  • <b>{c}</b>: {n} files" for c, n in sorted(cat_counts.items()))
            date_sample = "\n".join(f"  • {d}: {n}" for d, n in sorted(date_counts.items(), reverse=True)[:10])

            _tg_send(
                f"🔍 <b>Local Scan — {PC_NAME}</b>\n\n"
                f"📁 Base: <code>{base}</code>\n"
                f"📊 Total files: <b>{total_files}</b>\n\n"
                f"<b>By Category:</b>\n{cat_lines}\n\n"
                f"<b>Recent Dates (last 10):</b>\n{date_sample}\n\n"
                f"Use <code>/uploadold [Category] all</code> to upload any category."
            )
        except Exception as e:
            logging.error(f"_scan_and_report_local_thread: {e}")
            _tg_send(f"❌ Scan error on <b>{PC_NAME}</b>: {e}")

    def _check_duplicate(self, folder_path, fname):
        """
        Returns True ONLY if an identical file (same name = same paper/page/pos/size)
        already exists. Files with the same page but different size or position are
        NOT duplicates — they are allowed to save without any warning.
        """
        try:
            full_path = os.path.join(folder_path, fname)
            if os.path.exists(full_path):
                return True  # exact same filename = true duplicate
        except Exception:
            pass
        return False

    def _check_goal(self):
        if self.daily_goal > 0 and not self.daily_goal_notified:
            count = len(self.session_history)
            if count >= self.daily_goal:
                self.daily_goal_notified = True
                self.status_label.configure(text=f"🎯 Goal reached! {count}/{self.daily_goal} clips!", text_color=C_SUCCESS)
                threading.Thread(target=lambda: _tg_send(
                    f"🎯 <b>Daily goal reached on {PC_NAME}!</b>\n"
                    f"Saved {count}/{self.daily_goal} clips. Great work!"
                ), daemon=True).start()

    def _check_pending_upload(self):
        """Called on startup — if a scheduled upload is pending, run it."""
        pending = self.extra_settings.get("pending_upload_date")
        if not pending:
            return
        # Clear it first
        self.extra_settings.pop("pending_upload_date", None)
        self.save_settings()
        # _tg_send is a plain urllib call with a 10s timeout — called directly
        # here it used to block NAB's startup for up to 10s if Telegram was
        # slow to respond, for a notification nobody needs to wait on.
        threading.Thread(
            target=_tg_send,
            args=(f"⏰ <b>Running scheduled upload on {PC_NAME}</b>\n📅 Date: <b>{pending}</b>",),
            daemon=True
        ).start()
        threading.Thread(
            target=self._upload_date_list_thread,
            args=("*", [pending]),
            daemon=True
        ).start()
