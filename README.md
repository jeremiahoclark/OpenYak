# Yak

**Yak is a personal AI assistant that lives on your home network.** It connects to your favorite messaging apps — Discord, Telegram, Slack, Email, and more — so you can talk to it from anywhere, on any device. Ask it questions, have it check your calendar, search the web, generate images and videos, or schedule reminders. It runs 24/7 on your own hardware, keeping your data private.

Yak is designed for the **NVIDIA DGX Spark** (or any similar computer with a local GPU). It uses [Ollama](https://ollama.com) to run AI models directly on your machine — no cloud AI subscriptions required.

## What can Yak do?

- **Chat from anywhere** — Talk to Yak through Discord, Telegram, Slack, WhatsApp, Email, or several other platforms. Send a message from your phone and get a reply in seconds.
- **Check your calendar** — "What's on my schedule today?" Yak connects to Google Calendar and gives you a plain-English summary.
- **Search the web** — Ask Yak to look something up and it will search the internet and summarize what it finds.
- **Generate images and videos** — Describe what you want and Yak will create it using FLUX image generation, with optional art styles (Arcane, Devil May Cry, and more). It can then animate the image into a short video.
- **Schedule reminders and recurring tasks** — "Remind me to stretch every 2 hours" or "Send me a weather report every morning at 8am."
- **Read, write, and manage files** — Yak can work with files on your machine, run commands, and help with technical tasks.
- **Remember things** — Yak keeps conversation history and persistent memory across sessions.

## Requirements

- **NVIDIA DGX Spark** (or equivalent: any Linux/macOS machine with an NVIDIA GPU and 16+ GB of shared/unified memory)
- **Docker** (recommended) or Python 3.11+
- **Ollama** installed and running

## Quick start (Docker)

This is the easiest way to get Yak running. The Docker image includes everything — the AI model, image generation server, and all dependencies.

**1. Clone and configure**

```bash
git clone https://github.com/jeremiahoclark/OpenYak.git
cd yak
cp .env.example .env
```

Edit `.env` and fill in your bot tokens for whichever chat platforms you want to use (at minimum, set one like `YAK_CHANNELS__DISCORD__TOKEN` or `YAK_CHANNELS__TELEGRAM__TOKEN`).

**2. Build the Docker image**

```bash
docker build -t yak .
```

This will download the AI model and image generation model during the build, so it may take a while the first time.

**3. Run**

```bash
docker run --gpus all -p 18790:18790 yak
```

That's it. Yak will start up, connect to your chat platforms, and begin responding to messages.

## Quick start (without Docker)

If you prefer to run Yak directly:

```bash
# Install Ollama and pull a model
ollama pull nemotron-3-nano

# Install Yak
pip install -e .

# Configure
cp .env.example .env
# Edit .env with your settings

# Start the gateway (connects to all enabled chat platforms)
yak gateway
```

Or for a quick one-off chat in the terminal:

```bash
yak agent -m "Hello!"
```

## Connecting chat platforms

Yak supports many messaging platforms. You only need to set up the ones you want.

| Platform | What you need |
|----------|---------------|
| **Telegram** | A bot token from [@BotFather](https://t.me/BotFather) |
| **Discord** | A bot token from the [Developer Portal](https://discord.com/developers/applications) |
| **Slack** | A bot token + app token from [Slack API](https://api.slack.com/apps) |
| **Email** | IMAP/SMTP credentials (works with Gmail, Outlook, etc.) |
| **WhatsApp** | Scan a QR code to link your account |

For each platform, add the credentials to your `.env` file. See `.env.example` for all available settings.

### Example: Discord

1. Create a bot at [discord.com/developers](https://discord.com/developers/applications)
2. Enable **Message Content Intent** in the Bot settings
3. Generate an invite link (OAuth2 > bot scope > Send Messages + Read Message History)
4. Add to your `.env`:
   ```
   YAK_CHANNELS__DISCORD__TOKEN=your_bot_token_here
   ```
5. Invite the bot to your server and start chatting

### Example: Telegram

1. Message [@BotFather](https://t.me/BotFather) on Telegram and create a new bot
2. Add to your `.env`:
   ```
   YAK_CHANNELS__TELEGRAM__TOKEN=your_bot_token_here
   ```
3. Start chatting with your bot

## Google Calendar

Yak can read your Google Calendar using a service account (read-only access).

1. Create a service account in [Google Cloud Console](https://console.cloud.google.com/) with Calendar API enabled
2. Download the JSON key file
3. Share your Google Calendar with the service account's email address
4. Configure in `.env`:
   ```
   YAK_TOOLS__CALENDAR__ENABLED=true
   YAK_TOOLS__CALENDAR__SERVICE_ACCOUNT_KEY_FILE=/path/to/key.json
   YAK_TOOLS__CALENDAR__CALENDAR_ID=your_email@gmail.com
   YAK_TOOLS__CALENDAR__TIMEZONE=America/Chicago
   ```

## Image and video generation

Yak includes a built-in image generation server powered by FLUX.2 Klein. You can ask Yak to create images and animate them into short videos.

Available art styles (via LoRA):
- **Arcane** — Arcane / League of Legends visual style
- **Cyanide & Happiness** — Stick figure webcomic style
- **Devil May Cry** — DMC game art style

Just ask naturally: *"Draw me a sunset over Tokyo in the Arcane style and turn it into a video."*

## Scheduled tasks

Yak has a built-in scheduler for reminders and recurring tasks.

```bash
# Add a reminder
yak cron add --name "stretch" --message "Time to stretch!" --every 7200

# Daily digest at 8am
yak cron add --name "morning" --message "Good morning! Give me today's weather and calendar." --cron "0 8 * * *"

# List scheduled tasks
yak cron list
```

## CLI reference

| Command | What it does |
|---------|-------------|
| `yak gateway` | Start Yak and connect to all enabled chat platforms |
| `yak agent -m "..."` | Send a single message and get a response |
| `yak agent` | Start an interactive chat in the terminal |
| `yak status` | Show current configuration and status |
| `yak onboard` | First-time setup wizard |
| `yak cron list` | Show scheduled tasks |

## Project structure

```
yak/
  agent/        Core AI agent (reasoning loop, tool execution)
  channels/     Chat platform connectors (Discord, Telegram, etc.)
  integrations/ External services (Google Calendar, Fal video)
  workflows/    Multi-step pipelines (text to video)
  skills/       Bundled capabilities (weather, GitHub, tmux, etc.)
  providers/    LLM backends (Ollama, plus optional cloud providers)
  cron/         Task scheduler
  config/       Settings and environment loading
  cli/          Command-line interface
```

## Security

- Yak runs entirely on your own hardware. Your conversations and data stay on your machine.
- No data is sent to cloud AI services unless you explicitly configure a cloud LLM provider.
- Bot tokens and credentials are stored in your local `.env` file (never committed to git).
- See [SECURITY.md](SECURITY.md) for the full security policy.

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
