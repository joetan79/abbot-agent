"""
Skills system — load and apply custom skills from skills/ folder.
Add new .md skill files to teach ABbot new behaviors without changing core code.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SKILLS_DIR = Path("skills")

SKILL_PRIORITY = [
    "communication_style",   # highest priority
    "agent_behavior",        # core behavior
    "response_style",        # formatting
    "chinese_traditional",   # language rules
    "news_reporting",        # domain specific
    "crypto_reporting",      # domain specific
    "weather_reporting",     # domain specific
    "study_assistant",       # domain specific
    "xfeed_quality",         # xfeed source/format rules
]


def load_skills(scope: str = "all") -> str:
    """
    Load skill files in priority order.
    scope: "all", "news", "crypto", "study", "agent", "core"
    """
    if not SKILLS_DIR.exists():
        SKILLS_DIR.mkdir(exist_ok=True)
        return ""

    # Determine which skills to load
    scope_map = {
        "core": [
            "communication_style",
            "agent_behavior",
            "response_style",
            "chinese_traditional",
        ],
        "news": [
            "communication_style",
            "response_style",
            "news_reporting",
        ],
        "crypto": [
            "communication_style",
            "response_style",
            "crypto_reporting",
        ],
        "study": [
            "communication_style",
            "response_style",
            "chinese_traditional",
            "study_assistant",
        ],
        "weather": [
            "communication_style",
            "response_style",
            "weather_reporting",
        ],
        "xfeed": [
            "communication_style",
            "response_style",
            "xfeed_quality",
        ],
        "all": SKILL_PRIORITY,
    }

    skills_to_load = scope_map.get(scope, SKILL_PRIORITY)

    skill_texts = []
    total_tokens = 0

    for skill_name in skills_to_load:
        skill_file = SKILLS_DIR / f"{skill_name}.md"
        if not skill_file.exists():
            continue
        try:
            content = skill_file.read_text().strip()
            if content:
                # Rough token estimate (4 chars per token)
                tokens = len(content) // 4
                total_tokens += tokens
                skill_texts.append(content)
                logger.debug(
                    f"Loaded skill: {skill_name} "
                    f"(~{tokens} tokens)"
                )
        except Exception as e:
            logger.error(
                f"Failed to load {skill_name}: {e}")

    if not skill_texts:
        return ""

    logger.info(
        f"Skills loaded: {len(skill_texts)} files | "
        f"~{total_tokens} tokens"
    )

    return (
        "\n\nBEHAVIORAL GUIDELINES:\n" +
        "\n\n".join(skill_texts)
    )


def list_skills() -> list:
    """List all available skill files."""
    if not SKILLS_DIR.exists():
        return []
    files = sorted(SKILLS_DIR.glob("*.md"))
    return [f.stem for f in files]


def get_skill_token_estimate() -> dict:
    """Get token estimate for each skill."""
    if not SKILLS_DIR.exists():
        return {}
    estimates = {}
    for f in sorted(SKILLS_DIR.glob("*.md")):
        try:
            content = f.read_text().strip()
            estimates[f.stem] = len(content) // 4
        except Exception:
            estimates[f.stem] = 0
    return estimates
