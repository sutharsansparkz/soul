from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from rich import box
from rich.console import Console
from rich.table import Table

from soul.config import Settings, get_settings
from soul.memory.episodic import EpisodicMemoryRepository


def relative_time(iso_str: str, *, datetime_module=datetime) -> str:
    """Convert an ISO-8601 timestamp string to a human-relative label."""
    if not iso_str or iso_str == "-":
        return "-"
    try:
        dt = datetime_module.fromisoformat(iso_str)
    except ValueError:
        return iso_str
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime_module.now(timezone.utc) - dt
    days = delta.days
    if days < 0:
        return "just now"
    if days == 0:
        hours = delta.seconds // 3600
        if hours == 0:
            mins = delta.seconds // 60
            return f"{mins}m ago" if mins > 0 else "just now"
        return f"{hours}h ago"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 14:
        return "1 week ago"
    if days < 30:
        return f"{days // 7} weeks ago"
    if days < 60:
        return "1 month ago"
    months = days // 30
    if months < 12:
        return f"{months} months ago"
    years = days // 365
    return f"{years} year{'s' if years > 1 else ''} ago"


def record_hms_score(record) -> float:
    raw = record.metadata.get("hms_score", 0.5)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.5


def record_tier(record) -> str:
    return str(record.metadata.get("tier", "present"))


def score_bar(score: float, width: int = 12) -> str:
    filled = int(max(0, min(width, round(score * width))))
    return ("#" * filled) + ("." * (width - filled))


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def simple_similarity(query: str, content: str, *, settings_loader: Callable[[], Settings] = get_settings) -> float:
    settings = settings_loader()
    query_tokens = {token.casefold() for token in query.split() if token.strip()}
    if not query_tokens:
        return 0.0
    content_tokens = {token.casefold() for token in content.split() if token.strip()}
    overlap = len(query_tokens & content_tokens) / max(1, len(query_tokens))
    if query.casefold() in content.casefold():
        overlap += settings.memory_substring_boost
    return clamp01(overlap)


def record_retrieval_rank(record, *, query: str, settings_loader: Callable[[], Settings] = get_settings) -> float:
    raw = record.metadata.get("retrieval_rank")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    settings = settings_loader()
    semantic = simple_similarity(query, str(record.content), settings_loader=settings_loader)
    return (semantic * settings.hms_semantic_weight) + (record_hms_score(record) * settings.hms_score_weight)


def render_memories_overview(console: Console, settings: Settings, *, relative_time_func: Callable[[str], str] = relative_time) -> None:
    episodic_repo = EpisodicMemoryRepository(settings=settings)
    memories: list[dict[str, object]] = []
    for item in episodic_repo.list_top(limit=120):
        source = str(item.metadata.get("source") or "episodic")
        memories.append(
            {
                "source": source,
                "score": record_hms_score(item),
                "tier": record_tier(item),
                "when": relative_time_func(str(item.metadata.get("timestamp") or "-")),
                "content": str(item.content),
            }
        )

    if not memories:
        console.print("[dim]No memories stored yet.[/dim]")
        return

    memories.sort(key=lambda item: float(item["score"]), reverse=True)
    table = Table(title="Recent memories - sorted by HMS score", box=box.SIMPLE_HEAVY)
    table.add_column("Score", style="cyan", width=8)
    table.add_column("Bar", style="magenta", width=14)
    table.add_column("Tier", style="magenta", width=10)
    table.add_column("When", style="cyan", width=20)
    table.add_column("Content", style="white")
    tier_counts = {"vivid": 0, "present": 0, "fading": 0, "cold": 0, "manual": 0}
    for item in memories[:60]:
        score = float(item["score"])
        tier = str(item["tier"])
        source = str(item["source"])
        if source == "manual":
            tier_counts["manual"] = tier_counts.get("manual", 0) + 1
        else:
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        table.add_row(f"{score:.2f}", score_bar(score), tier, str(item["when"]), str(item["content"]))
    console.print(table)
    console.print(
        f"[dim]{tier_counts.get('vivid', 0)} vivid[/dim]  "
        f"[dim]{tier_counts.get('present', 0)} present[/dim]  "
        f"[dim]{tier_counts.get('fading', 0)} fading[/dim]  "
        f"[dim]{tier_counts.get('cold', 0)} cold[/dim]  "
        f"[dim]{tier_counts.get('manual', 0)} manual[/dim]"
    )


def search_memories(console: Console, settings: Settings, query: str) -> None:
    episodic_repo = EpisodicMemoryRepository(settings=settings)
    episodic = episodic_repo.search(query, limit=20)
    if not episodic:
        console.print("[dim]No matching memories found.[/dim]")
        return

    merged: list[dict[str, object]] = []
    for item in episodic:
        merged.append(
            {
                "source": str(item.metadata.get("source") or "episodic"),
                "score": record_hms_score(item),
                "tier": record_tier(item),
                "content": str(item.content),
                "rank": record_retrieval_rank(item, query=query),
            }
        )

    merged.sort(key=lambda row: float(row["rank"]), reverse=True)

    table = Table(title=f'Unified Memory Search: "{query}" (HMS reranked)', box=box.SIMPLE_HEAVY)
    table.add_column("Source", style="cyan", width=18)
    table.add_column("Score", style="cyan", width=8)
    table.add_column("Tier", style="magenta", width=10)
    table.add_column("Content", style="white")
    table.add_column("Rank", style="cyan", width=8)

    for item in merged[:20]:
        table.add_row(
            str(item["source"]),
            f"{float(item['score']):.2f}",
            str(item["tier"]),
            str(item["content"]),
            f"{float(item['rank']):.4f}",
        )
    console.print(table)


def show_top_memories(console: Console, settings: Settings) -> None:
    episodic_repo = EpisodicMemoryRepository(settings=settings)
    rows = episodic_repo.list_top(limit=10)
    if not rows:
        console.print("[dim]No memories stored yet.[/dim]")
        return
    table = Table(title="Top Memories (Most Vivid)", box=box.SIMPLE_HEAVY)
    table.add_column("Score", style="cyan", width=8)
    table.add_column("Tier", style="magenta", width=10)
    table.add_column("Source", style="dim", width=18)
    table.add_column("Content", style="white")
    for row in rows:
        source = str(row.metadata.get("source") or "") if hasattr(row, "metadata") else ""
        table.add_row(f"{record_hms_score(row):.2f}", record_tier(row), source, str(row.content))
    console.print(table)


def show_cold_memories(console: Console, settings: Settings, *, relative_time_func: Callable[[str], str] = relative_time) -> None:
    episodic_repo = EpisodicMemoryRepository(settings=settings)
    rows = episodic_repo.list_cold(limit=50)
    if not rows:
        console.print("[dim]No cold memories yet.[/dim]")
        return
    table = Table(title="Cold Memories", box=box.SIMPLE_HEAVY)
    table.add_column("Score", style="cyan", width=8)
    table.add_column("When", style="cyan", width=20)
    table.add_column("Content", style="white")
    for row in rows:
        table.add_row(
            f"{record_hms_score(row):.2f}",
            relative_time_func(str(row.metadata.get("timestamp", "-"))),
            str(row.content),
        )
    console.print(table)


def boost_memory(console: Console, settings: Settings, query: str) -> None:
    episodic_repo = EpisodicMemoryRepository(settings=settings)
    matches = episodic_repo.search(query, limit=5)
    if not matches:
        console.print("[dim]No matching memories found.[/dim]")
        return
    target = matches[0]
    memory_id = str(target.metadata.get("memory_id", target.id))
    before_row = episodic_repo.get_row(memory_id)
    before = float(before_row["hms_score"]) if before_row and "hms_score" in before_row else record_hms_score(target)
    updated = episodic_repo.boost(memory_id)
    after = float(updated["hms_score"]) if updated and "hms_score" in updated else before
    console.print(f"[green]Boosted memory.[/green] {before:.3f} -> {after:.3f}")
    console.print(f"[dim]{target.content}[/dim]")


def clear_memories(console: Console, settings: Settings) -> int:
    episodic_repo = EpisodicMemoryRepository(settings=settings)
    deleted = episodic_repo.clear()
    console.print(f"[green]Deleted {deleted} SQLite-backed memories.[/green]")
    return deleted
