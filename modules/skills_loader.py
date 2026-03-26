"""
Skills system — load and apply custom skills from skills/ folder.
Add new .md skill files to teach ABbot new behaviors without changing core code.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SKILLS_DIR = Path("skills")


def load_skills() -> str:
    """
    Load all skill files from skills/ folder.
    Returns combined skills prompt to inject into system prompts.
    """
    if not SKILLS_DIR.exists():
        SKILLS_DIR.mkdir(exist_ok=True)
        return ""

    skill_texts = []
    skill_files = list(SKILLS_DIR.glob("*.md")) + list(SKILLS_DIR.glob("*.txt"))

    if not skill_files:
        return ""

    for skill_file in sorted(skill_files):
        try:
            content = skill_file.read_text().strip()
            if content:
                skill_name = skill_file.stem.replace("_", " ").title()
                skill_texts.append(
                    f"=== Skill: {skill_name} ===\n{content}"
                )
                logger.info(f"Loaded skill: {skill_file.name}")
        except Exception as e:
            logger.error(f"Failed to load skill {skill_file}: {e}")

    if not skill_texts:
        return ""

    return (
        "\n\nLOADED SKILLS (apply these behaviors):\n"
        + "\n\n".join(skill_texts)
    )


def list_skills() -> list:
    """List all available skill files."""
    if not SKILLS_DIR.exists():
        return []
    return [
        f.name
        for f in sorted(
            list(SKILLS_DIR.glob("*.md")) + list(SKILLS_DIR.glob("*.txt"))
        )
    ]


def get_skill(skill_name: str) -> str:
    """Get content of a specific skill file."""
    skill_file = SKILLS_DIR / f"{skill_name}.md"
    if not skill_file.exists():
        skill_file = SKILLS_DIR / f"{skill_name}.txt"
    if skill_file.exists():
        return skill_file.read_text().strip()
    return ""
