# ABbot - Personal AI Agent

Telegram AI agent powered by Claude AI.

## Features
- Personal AI agent with memory and scheduling
- Family study assistant (homework, math, chinese)
- Real-time AI & Tech news via RSS feeds
- Live crypto prices via CoinGecko
- Weather reports
- Task management and daily reports
- Auto-publishes news to AI & Tech Daily website

## Setup
1. Clone repo
2. python3 -m venv venv
3. source venv/bin/activate
4. pip install -r requirements.txt
5. cp .env.example .env && nano .env
6. python bot.py

## Tech Stack
- Python 3.12
- python-telegram-bot 21.5
- Anthropic Claude API (Sonnet + Haiku)
- APScheduler
- RSS Feeds (feedparser)
- CoinGecko API
