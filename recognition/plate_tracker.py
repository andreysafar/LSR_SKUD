"""Трекинг номерных знаков между кадрами.

Подавление дубликатов, голосование по OCR-результатам,
временная консистентность для определения направления.
"""
import logging
import time
from collections import defaultdict
from typing import Dict, Optional, List, Any

logger = logging.getLogger(__name__)


class PlateTracker:
    """Track license plates across frames for a single camera."""

    def __init__(self, cooldown_seconds: float = 30.0,
                 vote_threshold: int = 2,
                 max_tracks: int = 100):
        """
        Args:
            cooldown_seconds: Minimum time between events for the same plate
            vote_threshold: Minimum readings before confirming a plate
            max_tracks: Maximum concurrent tracked plates (LRU eviction)
        """
        self.cooldown_seconds = cooldown_seconds
        self.vote_threshold = vote_threshold
        self.max_tracks = max_tracks

        # plate_number -> TrackInfo
        self._tracks: Dict[str, Dict[str, Any]] = {}

    def update(self, plate_number: str, confidence: float,
               bbox: tuple = None) -> Dict[str, Any]:
        """Update tracker with a new plate detection.

        Returns:
            Dict with keys:
                - confirmed: bool - True if plate is confirmed (enough readings)
                - is_new_event: bool - True if this is a new event (not duplicate)
                - best_plate: str - Best plate number from voting
                - best_confidence: float - Confidence of best plate
                - readings_count: int - Total readings for this plate
        """
        now = time.time()
        plate_clean = plate_number.upper().replace(" ", "")

        result = {
            "confirmed": False,
            "is_new_event": False,
            "best_plate": plate_clean,
            "best_confidence": confidence,
            "readings_count": 0,
        }

        if plate_clean in self._tracks:
            track = self._tracks[plate_clean]

            # Check cooldown
            elapsed = now - track["last_event_time"]
            if elapsed < self.cooldown_seconds:
                # Within cooldown - accumulate readings but don't trigger event
                track["readings"].append((plate_number, confidence))
                track["last_seen"] = now

                best = self._get_best_reading(track["readings"])
                result["best_plate"] = best[0]
                result["best_confidence"] = best[1]
                result["readings_count"] = len(track["readings"])
                result["confirmed"] = len(track["readings"]) >= self.vote_threshold
                return result
            else:
                # Cooldown expired - this is a new event
                track["readings"] = [(plate_number, confidence)]
                track["last_seen"] = now
                track["last_event_time"] = now

                result["is_new_event"] = True
                result["confirmed"] = True
                result["readings_count"] = 1
                return result
        else:
            # New plate
            self._evict_if_needed()
            self._tracks[plate_clean] = {
                "readings": [(plate_number, confidence)],
                "first_seen": now,
                "last_seen": now,
                "last_event_time": now,
            }

            result["is_new_event"] = True
            result["confirmed"] = self.vote_threshold <= 1
            result["readings_count"] = 1
            return result

    def _get_best_reading(self, readings: List[tuple]) -> tuple:
        """Get the most common plate reading weighted by confidence."""
        if not readings:
            return ("", 0.0)

        # Count occurrences weighted by confidence
        votes: Dict[str, float] = defaultdict(float)
        for plate, conf in readings:
            clean = plate.upper().replace(" ", "")
            votes[clean] += conf

        best_plate = max(votes, key=votes.get)
        # Average confidence for the best plate
        matching = [(p, c) for p, c in readings
                    if p.upper().replace(" ", "") == best_plate]
        avg_conf = sum(c for _, c in matching) / len(matching) if matching else 0.0

        return (best_plate, avg_conf)

    def _evict_if_needed(self):
        """Remove oldest tracks if at capacity."""
        if len(self._tracks) >= self.max_tracks:
            # Sort by last_seen, remove oldest quarter
            sorted_plates = sorted(
                self._tracks.keys(),
                key=lambda p: self._tracks[p]["last_seen"]
            )
            to_remove = sorted_plates[:self.max_tracks // 4]
            for plate in to_remove:
                del self._tracks[plate]

    def is_duplicate(self, plate_number: str) -> bool:
        """Check if plate was recently processed (within cooldown)."""
        plate_clean = plate_number.upper().replace(" ", "")
        if plate_clean not in self._tracks:
            return False

        elapsed = time.time() - self._tracks[plate_clean]["last_event_time"]
        return elapsed < self.cooldown_seconds

    def get_track_info(self, plate_number: str) -> Optional[Dict]:
        """Get tracking info for a plate."""
        plate_clean = plate_number.upper().replace(" ", "")
        return self._tracks.get(plate_clean)

    def cleanup(self, max_age_seconds: float = 300.0):
        """Remove stale tracks older than max_age_seconds."""
        now = time.time()
        to_remove = [
            plate for plate, track in self._tracks.items()
            if now - track["last_seen"] > max_age_seconds
        ]
        for plate in to_remove:
            del self._tracks[plate]

    def reset(self):
        """Clear all tracks."""
        self._tracks.clear()
