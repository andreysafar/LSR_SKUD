"""Кэш привязок метка↔номер т/с.

Кэширует данные из Parsec API чтобы не обращаться к серверу при каждом сканировании.
Обновление кэша — по таймеру (по умолчанию каждые 5 мин).
"""
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class TagCache:
    """In-memory cache: tag_code → {person_id, plates: set[str]}"""

    def __init__(self, parsec_api=None, refresh_interval_sec: int = 300):
        self.parsec = parsec_api
        self.refresh_interval = refresh_interval_sec
        self._cache: Dict[str, dict] = {}  # tag_code -> {person_id, plates, updated_at}
        self._person_tags: Dict[str, List[str]] = {}  # person_id -> [tag_codes]
        self._lock = threading.Lock()
        self._last_full_refresh: Optional[datetime] = None
        self._refresh_timer: Optional[threading.Timer] = None

    def start(self):
        """Start periodic refresh."""
        self._schedule_refresh()

    def stop(self):
        """Stop periodic refresh."""
        if self._refresh_timer:
            self._refresh_timer.cancel()
            self._refresh_timer = None

    def get_plates_for_tag(self, tag_code: str) -> Optional[Set[str]]:
        """Get cached plate numbers for a tag. Returns None if not cached."""
        with self._lock:
            entry = self._cache.get(tag_code)
            if entry:
                return set(entry["plates"])
        return None

    def get_person_for_tag(self, tag_code: str) -> Optional[str]:
        """Get person_id for tag from cache."""
        with self._lock:
            entry = self._cache.get(tag_code)
            return entry["person_id"] if entry else None

    def update_tag(self, tag_code: str, person_id: str, plates: List[str]):
        """Manually update single tag entry (e.g., after live Parsec lookup)."""
        with self._lock:
            self._cache[tag_code] = {
                "person_id": person_id,
                "plates": [p.upper().replace(" ", "") for p in plates],
                "updated_at": datetime.now(),
            }

    def refresh_all(self):
        """Full refresh: load all persons and their identifiers from Parsec."""
        if not self.parsec:
            return

        try:
            session_id = self.parsec.get_bot_session_id()
            if not session_id:
                logger.warning("TagCache: no Parsec session, skipping refresh")
                return

            # Get all identifiers (tags = type 0, plates = type 1)
            all_identifiers = self.parsec.get_all_identifiers(session_id)
            if all_identifiers is None:
                # Fallback: API not available, keep existing cache
                logger.warning("TagCache: get_all_identifiers not available")
                return

            # Group by person_id
            persons = {}  # person_id -> {tags: [], plates: []}
            for ident in all_identifiers:
                pid = ident.get("person_id")
                if not pid:
                    continue
                if pid not in persons:
                    persons[pid] = {"tags": [], "plates": []}

                itype = ident.get("identif_type", -1)
                code = ident.get("code", "")
                name = ident.get("name", "")

                if itype == 0 and code:  # RFID tag
                    persons[pid]["tags"].append(code)
                elif itype == 1 and name:  # License plate
                    persons[pid]["plates"].append(name.upper().replace(" ", ""))

            # Build cache
            new_cache = {}
            new_person_tags = {}
            now = datetime.now()
            for pid, data in persons.items():
                new_person_tags[pid] = data["tags"]
                for tag in data["tags"]:
                    new_cache[tag] = {
                        "person_id": pid,
                        "plates": data["plates"],
                        "updated_at": now,
                    }

            with self._lock:
                self._cache = new_cache
                self._person_tags = new_person_tags
                self._last_full_refresh = now

            logger.info("TagCache refreshed: %d tags, %d persons",
                        len(new_cache), len(persons))

        except Exception as e:
            logger.error("TagCache refresh failed: %s", e)

    def _schedule_refresh(self):
        """Schedule next periodic refresh."""
        self._refresh_timer = threading.Timer(
            self.refresh_interval, self._periodic_refresh
        )
        self._refresh_timer.daemon = True
        self._refresh_timer.start()

    def _periodic_refresh(self):
        """Periodic refresh callback."""
        try:
            self.refresh_all()
        finally:
            self._schedule_refresh()

    @property
    def stats(self) -> Dict:
        """Cache statistics."""
        with self._lock:
            return {
                "tags_cached": len(self._cache),
                "persons_cached": len(self._person_tags),
                "last_refresh": self._last_full_refresh.isoformat() if self._last_full_refresh else None,
            }
