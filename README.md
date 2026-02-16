# Yak

![Yak Tea Time](tea-time.gif)

## Here's the problem

I've watched animators spend more time hunting for reference images than actually animating.

They check Slack. Then Discord. Then Telegram. Then their calendar. Then back to Slack. By the time they find what they need, the creative momentum is gone.

The real work (crafting shots, refining performances, pushing boundaries) keeps getting pushed to the margins. Instead, teams drown in operational overhead: checking calendars, generating variations, managing files, coordinating schedules.

Bigger teams don't fix this. Tighter deadlines don't fix this. Better tools that require switching contexts definitely don't fix this.

## Meet Yak

Yak is a tool I built because I was tired of watching creative teams lose hours to administrative tasks.

It lives on your network and talks to you where you already work: Discord, Telegram, Slack, Email. No new apps to learn. No context switching.

Here's what matters: Yak runs entirely on your own hardware. Your conversations, your files, your work. Everything stays on your machine. No subscriptions. No data leaving your studio.

It handles the busywork so you can focus on the craft.

## What Yak Actually Does

**Automate the repetitive stuff**
- Ask Yak what's on your calendar today
- Generate reference images: "Show me 5 poses for a tired hero"
- Animate stills into short video previews
- Search the web and summarize what it finds
- Set reminders: "Tell me to review dailies at 5pm"

**Work with your actual files**
- Read, write, and organize files on your machine
- Run commands and scripts
- Remember things across conversations
- Help troubleshoot technical issues

**Stay connected**
- Chat from your phone, laptop, or terminal
- Get updates where you already hang out
- No need to open another app

**Generate assets**
- Create images with FLUX
- Apply art styles (Arcane, Devil May Cry, and more)
- Turn stills into animated previews

## What You Need

- **NVIDIA DGX Spark** or any Linux/Mac machine with an NVIDIA GPU and 16+ GB memory
- **Docker** (recommended) or Python 3.11+
- **Ollama** running locally

## Get Started (Docker)

This is the easiest path. The Docker image includes everything.

**1. Clone and configure**

```bash
git clone https://github.com/jeremiahoclark/OpenYak.git
cd yak
cp .env.example .env
```

Edit `.env` and add your bot tokens for whichever platforms you want to use. You only need one to start.

**2. Build**

```bash
docker build -t yak .
```

This downloads the models during build. First time takes a while.

**3. Run**

```bash
docker run --gpus all -p 18790:18790 yak
```

That's it. Yak connects to your platforms and starts responding.

## Get Started (No Docker)

If you prefer running directly:

```bash
# Install Ollama and get a model
ollama pull nemotron-3-nano

# Install Yak
pip install -e .

# Configure
cp .env.example .env
# Edit .env with your settings

# Start
yak gateway
```

Or just chat once in your terminal:

```bash
yak agent -m "Hello!"
```

## Connect Your Platforms

Yak supports the platforms you already use. Set up one or all of them.

| Platform | What you need |
|----------|---------------|
| **Telegram** | Bot token from [@BotFather](https://t.me/BotFather) |
| **Discord** | Bot token from [Discord Developer Portal](https://discord.com/developers/applications) |
| **Slack** | Bot token + app token from [Slack API](https://api.slack.com/apps) |
| **Email** | IMAP/SMTP credentials (Gmail, Outlook, etc.) |
| **WhatsApp** | Scan a QR code to link your account |

Add credentials to your `.env` file. See `.env.example` for all options.

### Discord Example

1. Create a bot at [discord.com/developers](https://discord.com/developers/applications)
2. Enable **Message Content Intent** in Bot settings
3. Generate an invite link (OAuth2 > bot scope > Send Messages + Read Message History)
4. Add to `.env`:
   ```
   YAK_CHANNELS__DISCORD__TOKEN=your_token_here
   ```
5. Invite the bot and start chatting

### Telegram Example

1. Message [@BotFather](https://t.me/BotFather) and create a new bot
2. Add to `.env`:
   ```
   YAK_CHANNELS__TELEGRAM__TOKEN=your_token_here
   ```
3. Start chatting

## Google Calendar

Yak can read your calendar using a service account (read-only).

1. Create a service account in [Google Cloud Console](https://console.cloud.google.com/) with Calendar API enabled
2. Download the JSON key file
3. Share your calendar with the service account email
4. Configure in `.env`:
   ```
   YAK_TOOLS__CALENDAR__ENABLED=true
   YAK_TOOLS__CALENDAR__SERVICE_ACCOUNT_KEY_FILE=/path/to/key.json
   YAK_TOOLS__CALENDAR__CALENDAR_ID=your_email@gmail.com
   YAK_TOOLS__CALENDAR__TIMEZONE=America/Chicago
   ```

## Image and Video Generation

Yak includes FLUX.2 Klein for image generation. You can create images and animate them.

**Art styles available:**
- **Arcane**: Arcane / League of Legends style
- **Cyanide & Happiness**: Stick figure webcomic style
- **Devil May Cry**: DMC game art style

Example: Tell Yak to draw a sunset over Tokyo in the Arcane style and animate it into a video.

## Scheduled Tasks

Yak has a scheduler for reminders and recurring tasks.

```bash
# Add a reminder
yak cron add --name "stretch" --message "Time to stretch!" --every 7200

# Daily digest at 8am
yak cron add --name "morning" --message "Good morning! Give me today's weather and calendar." --cron "0 8 * * *"

# List tasks
yak cron list
```

## CLI Commands

| Command | What it does |
|---------|-------------|
| `yak gateway` | Start Yak and connect to all enabled platforms |
| `yak agent -m "..."` | Send one message and get a response |
| `yak agent` | Interactive chat in terminal |
| `yak status` | Show configuration and status |
| `yak onboard` | First-time setup wizard |
| `yak cron list` | Show scheduled tasks |

## Project Structure

```
yak/
  agent/        Core reasoning and tool execution
  channels/     Platform connectors (Discord, Telegram, etc.)
  integrations/ External services (Calendar, video generation)
  workflows/    Multi-step pipelines
  skills/       Capabilities (weather, GitHub, etc.)
  providers/    LLM backends (Ollama, optional cloud)
  cron/         Task scheduler
  config/       Settings and environment
  cli/          Command-line interface
```

## Security

- Yak runs on your hardware. Your data stays on your machine.
- No data sent to cloud AI services unless you configure a cloud provider.
- Tokens and credentials live in your local `.env` file (never committed).
- See [SECURITY.md](SECURITY.md) for full policy.

## License

Apache 2.0. See [LICENSE](LICENSE) for details.

---

Cheers,

Jeremiah
