"""Goal & habit tracker: set goals, log completions, track streaks."""

import json
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
GOALS_FILE = "data/goals.json"


def _load() -> dict:
    try:
        with open(GOALS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict):
    tmp = GOALS_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, GOALS_FILE)
    except Exception as e:
        logger.error(f"[Goals] Save failed: {e}")


def _next_id() -> str:
    goals = _load()
    nums = [int(k[1:]) for k in goals if k.startswith("g") and k[1:].isdigit()]
    return f"g{max(nums, default=0) + 1:03d}"


def add_goal(description: str, frequency: str = "daily", target_per_week: int = None) -> str:
    goals = _load()
    gid = _next_id()
    goals[gid] = {
        "id": gid,
        "description": description,
        "frequency": frequency,
        "target_per_week": target_per_week or (7 if frequency == "daily" else 1),
        "completions": [],
        "created": datetime.now().isoformat(),
        "active": True,
    }
    _save(goals)
    logger.info(f"[Goals] Added: {gid} — {description}")
    return gid


def log_completion(goal_id: str) -> bool:
    goals = _load()
    if goal_id not in goals:
        return False
    goals[goal_id]["completions"].append(datetime.now().isoformat())
    _save(goals)
    return True


def remove_goal(goal_id: str) -> bool:
    goals = _load()
    if goal_id not in goals:
        return False
    goals[goal_id]["active"] = False
    _save(goals)
    return True


def get_streak(goal_id: str) -> int:
    """Returns current consecutive-day streak for a daily goal."""
    goals = _load()
    g = goals.get(goal_id)
    if not g:
        return 0
    completions = sorted(g.get("completions", []), reverse=True)
    if not completions:
        return 0
    streak = 0
    check_date = datetime.now().date()
    for c in completions:
        c_date = datetime.fromisoformat(c).date()
        if c_date == check_date or c_date == check_date - timedelta(days=streak):
            streak += 1
            check_date = c_date - timedelta(days=1)
        else:
            break
    return streak


def completions_this_week(goal_id: str) -> int:
    goals = _load()
    g = goals.get(goal_id, {})
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    return sum(1 for c in g.get("completions", []) if c >= cutoff)


def list_goals() -> list:
    goals = _load()
    result = []
    for gid, g in goals.items():
        if not g.get("active", True):
            continue
        streak = get_streak(gid)
        week_count = completions_this_week(gid)
        result.append({
            "id": gid,
            "description": g["description"],
            "frequency": g["frequency"],
            "streak": streak,
            "this_week": week_count,
            "target_per_week": g.get("target_per_week", 7),
        })
    return result


def get_goals_summary() -> str:
    """Compact summary for weekly report and system prompt."""
    goals_list = list_goals()
    if not goals_list:
        return ""
    lines = ["ACTIVE GOALS:"]
    for g in goals_list:
        bar = "█" * g["this_week"] + "░" * max(0, g["target_per_week"] - g["this_week"])
        lines.append(
            f"• {g['id']} {g['description']} | "
            f"streak {g['streak']}d | this week {g['this_week']}/{g['target_per_week']} [{bar}]"
        )
    return "\n".join(lines)
