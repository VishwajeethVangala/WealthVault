"""Persistent storage engine for the Agent Boardroom.

Persists active directives, historical resolutions, and the real-time debate timeline
across application restarts in Azure Table Storage.
"""

import asyncio
import concurrent.futures
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agents.forensic_crawler import clean_symbol
from core.agents.models import DirectiveCard, DirectiveStatus, TimelineEvent
from storage.tables.repositories import BoardroomRepository

logger = logging.getLogger("wealthvault.agents.storage")

DEFAULT_OWNER = "demo_reviewer"
PRIMARY_OWNER = "google_109909149391234323377"

_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def _run_sync(coro):
    """Run an async coroutine to completion and return its value synchronously.
    
    Safe whether called outside an event loop or inside an active event loop (e.g. FastAPI/Uvicorn).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        def worker():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        return _thread_pool.submit(worker).result()
    else:
        try:
            return asyncio.run(coro)
        except Exception as exc:
            logger.warning("Could not run sync table operation: %s", exc)
            return None


def _run_bg(coro):
    """Run an async coroutine in the background (fire-and-forget write)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        return asyncio.create_task(coro)
    else:
        def worker():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        _thread_pool.submit(worker)


class BoardroomStorage:
    """Manages Azure Table-backed persistence of agent directives and debate timelines."""

    def __init__(self, filepath: Optional[Path] = None):
        # filepath is only set in localized unit test environments (e.g. TestClient with tempdir)
        self.filepath: Optional[Path] = Path(filepath) if filepath else None
        self.repo: BoardroomRepository = BoardroomRepository()
        self._directives: Dict[str, Dict[str, DirectiveCard]] = {}  # owner_id -> {directive_id -> DirectiveCard}
        self._timeline: Dict[str, List[TimelineEvent]] = {}  # owner_id -> [TimelineEvent]
        self._last_mtime: float = 0.0

        if self.filepath:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            self._load_file()
        else:
            self._initial_table_load(PRIMARY_OWNER)
            self._initial_table_load(DEFAULT_OWNER)

    def _resolve_owner(self, owner_id: Optional[str] = None) -> str:
        """Resolve owner identifier with sensible fallback."""
        return (owner_id or PRIMARY_OWNER).strip()

    def _initial_table_load(self, owner_id: str) -> None:
        """Warm up in-memory cache from Azure Table Storage."""
        try:
            directives = _run_sync(self.repo.list_directives(owner_id=owner_id))
            if directives is not None:
                self._directives[owner_id] = {d.directive_id: d for d in directives}
            timeline = _run_sync(self.repo.get_timeline(owner_id=owner_id, limit=100))
            if timeline is not None:
                self._timeline[owner_id] = timeline
            logger.info("Initialized BoardroomStorage from Azure Table for user %s: %d directives, %d events",
                        owner_id, len(self._directives.get(owner_id, {})), len(self._timeline.get(owner_id, [])))
        except Exception as exc:
            logger.warning("Initial table load note for %s: %s", owner_id, exc)

    def _ensure_loaded(self, owner_id: Optional[str] = None):
        """Ensure the specified owner's state is loaded."""
        if self.filepath:
            try:
                if self.filepath.exists():
                    mtime = os.path.getmtime(self.filepath)
                    if mtime > self._last_mtime:
                        self._load_file()
            except Exception:
                pass
            return

        resolved_owner = self._resolve_owner(owner_id)
        if resolved_owner not in self._directives or not self._directives[resolved_owner]:
            self._initial_table_load(resolved_owner)
            # If still empty, attempt fallback to PRIMARY_OWNER or DEFAULT_OWNER or global
            if not self._directives.get(resolved_owner):
                for fallback in (PRIMARY_OWNER, DEFAULT_OWNER, "global"):
                    if fallback != resolved_owner and fallback in self._directives and self._directives[fallback]:
                        self._directives[resolved_owner] = dict(self._directives[fallback])
                        self._timeline[resolved_owner] = list(self._timeline.get(fallback, []))
                        break

    def _load_file(self):
        """Load state from local file (used ONLY in unit tests with explicit filepath)."""
        if not self.filepath or not self.filepath.exists():
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
                    canonical_map[card.directive_id] = card
                except Exception as exc:
                    logger.debug("Skipping card %s: %s", k, exc)
            self._directives[DEFAULT_OWNER] = canonical_map
            raw_timeline = data.get("timeline", [])
            self._timeline[DEFAULT_OWNER] = [TimelineEvent(**t) for t in raw_timeline]
        except Exception as exc:
            logger.warning("Could not load boardroom state from file %s: %s", self.filepath, exc)

    def _save_file(self):
        """Save state to local file (used ONLY in unit tests with explicit filepath)."""
        if not self.filepath:
            return
        try:
            temp_path = self.filepath.with_suffix(".tmp")
            user_dirs = self._directives.get(DEFAULT_OWNER, {})
            user_timeline = self._timeline.get(DEFAULT_OWNER, [])
            data = {
                "directives": {k: v.model_dump() for k, v in user_dirs.items()},
                "timeline": [t.model_dump() for t in user_timeline[-100:]]
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
            logger.warning("Could not persist test state to %s: %s", self.filepath, exc)

    def save_directive(self, directive: DirectiveCard, owner_id: Optional[str] = None):
        """Save or update an action directive without creating duplicates in Azure Tables."""
        resolved_owner = self._resolve_owner(owner_id)
        self._ensure_loaded(resolved_owner)
        user_dirs = self._directives.setdefault(resolved_owner, {})

        # 1:1 holding enforcement: remove any other active directive for the same (symbol, broker)
        act = directive.actions[0] if directive.actions else None
        if act:
            sym = clean_symbol(act.symbol).upper()
            brk = (act.broker or "broker").lower()
            to_remove = []
            for k, existing in user_dirs.items():
                if k != directive.directive_id and existing.actions:
                    e_act = existing.actions[0]
                    e_sym = clean_symbol(e_act.symbol).upper()
                    e_brk = (e_act.broker or "broker").lower()
                    if e_sym == sym and e_brk == brk:
                        to_remove.append(k)
            for k in to_remove:
                old_card = user_dirs.pop(k, None)
                if old_card and old_card.user_status != DirectiveStatus.PENDING_REVIEW:
                    directive.user_status = old_card.user_status
                    directive.user_comment = old_card.user_comment
                    directive.resolved_at = old_card.resolved_at
                # Delete duplicate from Azure Table
                if not self.filepath:
                    _run_bg(self.repo.delete_directive(resolved_owner, k))

        existing = user_dirs.get(directive.directive_id)
        if existing and existing.user_status != DirectiveStatus.PENDING_REVIEW:
            directive.user_status = existing.user_status
            directive.user_comment = existing.user_comment
            directive.resolved_at = existing.resolved_at

        user_dirs[directive.directive_id] = directive

        if self.filepath:
            self._save_file()
        else:
            # Persist directly to Azure Table Storage
            _run_bg(self.repo.upsert_directive(resolved_owner, directive))

    def get_directive(self, directive_id: str, owner_id: Optional[str] = None) -> Optional[DirectiveCard]:
        """Fetch a directive by its unique ID."""
        resolved_owner = self._resolve_owner(owner_id)
        self._ensure_loaded(resolved_owner)
        user_dirs = self._directives.get(resolved_owner, {})
        if directive_id in user_dirs:
            return user_dirs[directive_id]
        # Check fallbacks
        for fb in (PRIMARY_OWNER, DEFAULT_OWNER, "global"):
            if fb in self._directives and directive_id in self._directives[fb]:
                return self._directives[fb][directive_id]
        return None

    def list_directives(self, status: Optional[DirectiveStatus] = None, owner_id: Optional[str] = None) -> List[DirectiveCard]:
        """Return directives, optionally filtered by user status."""
        resolved_owner = self._resolve_owner(owner_id)
        self._ensure_loaded(resolved_owner)
        user_dirs = self._directives.get(resolved_owner, {})
        items = list(user_dirs.values())
        if status:
            items = [d for d in items if d.user_status == status]
        items.sort(key=lambda d: d.timestamp, reverse=True)
        return items

    def update_directive_status(
        self,
        directive_id: str,
        new_status: DirectiveStatus,
        user_comment: Optional[str] = None,
        owner_id: Optional[str] = None
    ) -> Optional[DirectiveCard]:
        """Update a directive's closure status (e.g., 'ORDER_PLACED_AT_BROKER') in Azure Tables."""
        resolved_owner = self._resolve_owner(owner_id)
        self._ensure_loaded(resolved_owner)
        directive = self.get_directive(directive_id, owner_id=resolved_owner)
        if not directive:
            return None

        directive.user_status = new_status
        directive.user_comment = user_comment
        directive.resolved_at = datetime.now(timezone.utc).isoformat()

        # Update in-memory
        self._directives.setdefault(resolved_owner, {})[directive_id] = directive

        # Log timeline event
        event = TimelineEvent(
            event_id=f"evt_user_{int(datetime.now(timezone.utc).timestamp())}",
            agent_id="user",
            agent_name="Investor (You)",
            event_type="USER_ACTION",
            message=f"Marked directive '{directive.title}' as {new_status.value}. {user_comment or ''}".strip(),
            directive_id=directive_id
        )
        self.add_timeline_event(event, owner_id=resolved_owner)

        if self.filepath:
            self._save_file()
        else:
            _run_bg(self.repo.upsert_directive(resolved_owner, directive))

        return directive

    def add_timeline_event(self, event: TimelineEvent, owner_id: Optional[str] = None):
        """Record an event to the public debate timeline in Azure Tables."""
        resolved_owner = self._resolve_owner(owner_id)
        self._ensure_loaded(resolved_owner)
        user_timeline = self._timeline.setdefault(resolved_owner, [])
        user_timeline.append(event)

        if self.filepath:
            self._save_file()
        else:
            _run_bg(self.repo.add_timeline_event(resolved_owner, event))

    def get_timeline(self, limit: int = 50, owner_id: Optional[str] = None) -> List[TimelineEvent]:
        """Fetch recent timeline events, newest first."""
        resolved_owner = self._resolve_owner(owner_id)
        self._ensure_loaded(resolved_owner)
        events = sorted(self._timeline.get(resolved_owner, []), key=lambda e: e.timestamp, reverse=True)
        return events[:limit]


# Global singleton instance
_boardroom_storage = BoardroomStorage()


def get_boardroom_storage() -> BoardroomStorage:
    return _boardroom_storage
