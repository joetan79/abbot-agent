# xfeed Quality Rules

## Source Priority
- ALWAYS prefer direct lab/researcher URLs over aggregator pages
- Skip techstartups.com, venturebeat roundups, syncedreview aggregations
- If source URL is a homepage or category page, discard it

## Output Format (strict)
Each item MUST follow this exact format:
SOURCE: [Lab or researcher name]
TITLE: [Announcement title — no lab name prefix]
URL: [Direct article URL]
DATE: [ISO date YYYY-MM-DD]
WHY: [One sentence: what changed and why it matters]

## Content Rules
- Only include announcements from the past 48 hours
- Only include primary announcements: model releases, research papers, product launches, major updates
- Skip opinion pieces, interviews, listicles, roundups
- Skip anything without a direct traceable URL
- Max 10 items, sorted newest first

## Source Extraction
- Strip "LabName - " or "LabName: " prefix from titles
- If SOURCE field is missing, infer from title or URL domain
- Known lab domains: openai.com, anthropic.com, deepmind.google, ai.meta.com, mistral.ai, deepseek.com, huggingface.co

## Deduplication
- Drop items where >60% of title words overlap with an already-included item
- Prefer the item with the more specific/direct URL
