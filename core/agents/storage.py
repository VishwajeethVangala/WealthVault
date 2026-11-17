"""Persistent storage engine for the Agent Boardroom.

Persists active directives, historical resolutions, and the real-time debate timeline
across application restarts in JSON storage.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from core.agents.forensic_crawler import clean_symbol
from core.agents.models import DirectiveCard, DirectiveStatus, TimelineEvent

logger = logging.getLogger("wealthvault.agents.storage")

STORAGE_PATH = Path("storage/blobs/boardroom_state.json")


class BoardroomStorage:
    """Manages file-backed persistence of agent directives and debate timelines."""

    def __init__(self, filepath: Optional[Path] = None):
        self.filepath = filepath or STORAGE_PATH
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._directives: Dict[str, DirectiveCard] = {}
        self._timeline: List[TimelineEvent] = []
        self._last_mtime: float = 0.0
        self._load()

    def _ensure_loaded(self):
        """Check if underlying file was updated externally and reload if needed."""
        try:
            if self.filepath.exists():
                mtime = os.path.getmtime(self.filepath)
                if mtime > self._last_mtime:
                    self._load()
        except Exception:
            pass

    def _load(self):
        """Load state from disk with automatic canonical deduplication."""
        if not self.filepath.exists():
            return
        try:
            self._last_mtime = os.path.getmtime(self.filepath)
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_directives = data.get("directives", {})
            canonical_map: Dict[str, DirectiveCard] = {}
            for k, v in raw_directives.items():
                try:
                    card = DirectiveCard(**v)
                    act = card.actions[0] if card.actions else None
                    if act:
                        sym = clean_symbol(act.symbol).upper()
                        brk = (act.broker or "broker").lower()
                        act_type = (act.action.value if hasattr(act.action, "value") else str(act.action)).lower()
                        canonical_id = f"dir_{sym}_{brk}_{act_type}"
                    else:
                        canonical_id = k

                    card.directive_id = canonical_id
                    if canonical_id in canonical_map:
                        existing = canonical_map[canonical_id]
                        if existing.user_status != DirectiveStatus.PENDING_REVIEW and card.user_status == DirectiveStatus.PENDING_REVIEW:
                            continue
                        if card.timestamp >= existing.timestamp:
                            canonical_map[canonical_id] = card
                    else:
                        canonical_map[canonical_id] = card
                except Exception as exc:
                    logger.debug("Skipping malformed directive card %s: %s", k, exc)

            self._directives = canonical_map
            raw_timeline = data.get("timeline", [])
            self._timeline = [TimelineEvent(**t) for t in raw_timeline]
            logger.info("Loaded %d unique directives and %d timeline events from disk", len(self._directives), len(self._timeline))
        except Exception as exc:
            logger.warning("Could not load boardroom state from %s: %s", self.filepath, exc)

    def _save(self):
        """Save state to disk safely on Windows."""
        try:
            temp_path = self.filepath.with_suffix(".tmp")
            data = {
                "directives": {k: v.model_dump() for k, v in self._directives.items()},
                "timeline": [t.model_dump() for t in self._timeline[-100:]]  # keep last 100 timeline events
            }
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            try:
                os.replace(temp_path, self.filepath)
            except OSError:
                with open(self.filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning("Could not persist boardroom state to %s: %s", self.filepath, exc)

    def save_directive(self, directive: DirectiveCard):
        """Save or update an action directive without creating duplicates."""
        existing = self._directives.get(directive.directive_id)
        if existing and existing.user_status != DirectiveStatus.PENDING_REVIEW:
            # Preserve user's closure status (e.g. ORDER_PLACED_AT_BROKER, IGNORED)
            directive.user_status = existing.user_status
            directive.user_comment = existing.user_comment
            directive.resolved_at = existing.resolved_at

        self._directives[directive.directive_id] = directive
        self._save()

    def get_directive(self, directive_id: str) -> Optional[DirectiveCard]:
        """Fetch a directive by its unique ID."""
        self._ensure_loaded()
        return self._directives.get(directive_id)

    def list_directives(self, status: Optional[DirectiveStatus] = None) -> List[DirectiveCard]:
        """Return directives, optionally filtered by user status."""
        self._ensure_loaded()
        items = list(self._directives.values())
        if status:
            items = [d for d in items if d.user_status == status]
        # Sort by timestamp descending (newest first)
        items.sort(key=lambda d: d.timestamp, reverse=True)
        return items

    def update_directive_status(
        self,
        directive_id: str,
        new_status: DirectiveStatus,
        user_comment: Optional[str] = None
    ) -> Optional[DirectiveCard]:
        """Update a directive's closure status (e.g., 'ORDER_PLACED_AT_BROKER')."""
        directive = self._directives.get(directive_id)
        if not directive:
            return None
        directive.user_status = new_status
        directive.user_comment = user_comment
        directive.resolved_at = datetime.now(timezone.utc).isoformat()
        self._save()

        # Log timeline event
        self.add_timeline_event(
            TimelineEvent(
                event_id=f"evt_user_{int(datetime.now(timezone.utc).timestamp())}",
                agent_id="user",
                agent_name="Investor (You)",
                event_type="USER_ACTION",
                message=f"Marked directive '{directive.title}' as {new_status.value}. {user_comment or ''}".strip(),
                directive_id=directive_id
            )
        )
        return directive

    def add_timeline_event(self, event: TimelineEvent):
        """Record an event to the public debate timeline."""
        self._timeline.append(event)
        self._save()

    def get_timeline(self, limit: int = 50) -> List[TimelineEvent]:
        """Fetch recent timeline events, newest first."""
        self._ensure_loaded()
        events = sorted(self._timeline, key=lambda e: e.timestamp, reverse=True)
        return events[:limit]


# Global singleton instance
_boardroom_storage = BoardroomStorage()

def get_boardroom_storage() -> BoardroomStorage:
    return _boardroom_storage
