# Mobile Verification Toolkit (MVT)
# Copyright (c) 2021 The MVT Project Authors.
# Use of this software is governed by the MVT License 1.1 that can be found at
#   https://license.mvt.re/1.1/

import io
import sqlite3

import biplist

from mvt.common.utils import (convert_mactime_to_unix,
                              convert_timestamp_to_iso, keys_bytes_to_string)

from .base import IOSExtraction

SAFARI_BROWSER_STATE_BACKUP_IDS = [
    "3a47b0981ed7c10f3e2800aa66bac96a3b5db28e",
]
SAFARI_BROWSER_STATE_ROOT_PATHS = [
    "private/var/mobile/Library/Safari/BrowserState.db",
    "private/var/mobile/Containers/Data/Application/*/Library/Safari/BrowserState.db",
]

class SafariBrowserState(IOSExtraction):
    """This module extracts all Safari browser state records."""

    def __init__(self, file_path=None, base_folder=None, output_folder=None,
                 fast_mode=False, log=None, results=[]):
        super().__init__(file_path=file_path, base_folder=base_folder,
                         output_folder=output_folder, fast_mode=fast_mode,
                         log=log, results=results)

    def serialize(self, record):
        return {
            "timestamp": record["last_viewed_timestamp"],
            "module": self.__class__.__name__,
            "event": "tab",
            "data": f"{record['tab_title']} - {record['tab_url']}"
        }

    def check_indicators(self):
        if not self.indicators:
            return

        for result in self.results:
            if "tab_url" in result and self.indicators.check_domain(result["tab_url"]):
                self.detected.append(result)
                continue

            if not "session_data" in result:
                continue

            for session_entry in result["session_data"]:
                if "entry_url" in session_entry and self.indicators.check_domain(session_entry["entry_url"]):
                    self.detected.append(result)

    def run(self):
        self._find_ios_database(backup_ids=SAFARI_BROWSER_STATE_BACKUP_IDS,
                                root_paths=SAFARI_BROWSER_STATE_ROOT_PATHS)
        self.log.info("Found Safari browser state database at path: %s", self.file_path)

        conn = sqlite3.connect(self.file_path)

        # Fetch valid icon cache.
        cur = conn.cursor()
        cur.execute("""SELECT
                tabs.title,
                tabs.url,
                tabs.user_visible_url,
                tabs.last_viewed_time,
                tab_sessions.session_data
            FROM tabs
            JOIN tab_sessions ON tabs.uuid = tab_sessions.tab_uuid
            ORDER BY tabs.last_viewed_time;""")

        session_history_count = 0
        for item in cur:
            session_entries = []

            if item[4]:
                # Skip a 4 byte header before the plist content.
                session_plist = item[4][4:]
                session_data = biplist.readPlist(io.BytesIO(session_plist))
                session_data = keys_bytes_to_string(session_data)

                if "SessionHistoryEntries" in session_data["SessionHistory"]:
                    for session_entry in session_data["SessionHistory"]["SessionHistoryEntries"]:
                        session_history_count += 1
                        session_entries.append(dict(
                            entry_title=session_entry["SessionHistoryEntryOriginalURL"],
                            entry_url=session_entry["SessionHistoryEntryURL"],
                            data_length=len(session_entry["SessionHistoryEntryData"]) if "SessionHistoryEntryData" in session_entry else 0,
                        ))

            self.results.append(dict(
                tab_title=item[0],
                tab_url=item[1],
                tab_visible_url=item[2],
                last_viewed_timestamp=convert_timestamp_to_iso(convert_mactime_to_unix(item[3])),
                session_data=session_entries,
            ))

        self.log.info("Extracted a total of %d tab records and %d session history entries",
                      len(self.results), session_history_count)
