# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Bot
```bash
# Run the bot locally
uv run -m src.main

# Run with Docker
docker build -t padel-bot .
docker run -e BOT_TOKEN="your_token" -e DATABASE_URL="your_db_url" padel-bot
```

### Package Management
```bash
# Install dependencies
uv sync

# Add new dependency
uv add <package_name>
```

### Environment Setup
Required environment variables:
- `BOT_TOKEN` - Telegram bot token (required)
- `DATABASE_URL` - PostgreSQL connection URL (optional, defaults to local)

## Architecture Overview

This is a Telegram Bot built with aiogram 3.x for managing padel game registrations. The bot allows users to register for games, create new games, and receive automated reminders.

### Core Components

**Database Layer (`src/database/`)**
- `db.py` - Main database class with connection pooling via asyncpg
- `queries.py` - SQL queries stored as constants
- `GameSlot` dataclass represents game entities with player slots (1-4)

**Services (`src/services/`)**
- `core.py` - Core bot utilities, formatters, and configurations
- `game_creation.py` - Game creation workflow with step-by-step forms
- `payments.py` - Payment processing handlers
- `scheduler.py` - Reminder system that runs background tasks

**Bot Framework**
- `main.py` - Entry point with middleware, router setup, and service initialization
- `handlers.py` - Main bot command handlers (/start, /games, menu interactions)
- `keyboards.py` - Inline keyboard definitions
- `config.py` - Configuration loading and logger setup using loguru

### Key Patterns

**Middleware System**: `DatabaseMiddleware` injects database and bot instances into all handlers via the `data` dict.

**Router Architecture**: The bot uses multiple routers (handlers, payments, game_creation) that are registered with the main dispatcher.

**Service Initialization**: Services are configured with dataclass configs (BotConfig, GameCreationConfig, ReminderConfig) and initialized during startup.

**Game Management**: Games are stored with 4 player slots (player_1 through player_4), supporting registration/unregistration operations.

**Async Database Operations**: All database operations use connection pooling and async context managers for proper resource management.

## Development Notes

- The codebase uses Python 3.13+ with modern async/await patterns
- Database schema expects PostgreSQL with specific table structure for games and users
- Logging is handled by loguru with both console and file output
- The bot supports pagination for game lists (configurable games_per_page)
- All user-facing text is in Russian
- Uses uv for dependency management instead of pip/poetry