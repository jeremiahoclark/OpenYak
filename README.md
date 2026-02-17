# Yak

![Yak Tea Time](tea-time.gif)

Animation, which was once reserved for children's cartoons, has entered a global new age. Demand for rich stories from perspectives of people all over the world has grown tremendously. With it, the consumer's appetite for dynamic animation. In 2025, *Solo Leveling* Season 2 won Anime of the Year. While the plot was good, what left watchers breathless was the extraordinary beauty and attention to detail of the combat scenes. This takes animators an extremely long time to produce (as long as one year for a single fight scene). Not to mention the countless other tasks animators have to work on, like world building "B-roll" shots and side character design and development. The standards for animators are high: not only do they have a wide range of work to do, they are expected to do it at an exceptional level of quality.

Yak is an answer to the overstretched animator. In the same way that Claude Code can extend an engineer's capabilities, Yak is designed to extend an animator's.

Yak has a couple of important features that allow it to do so:

**1) The artist's art is protected, because Yak runs locally.** The generations, fine-tuning, and artistic style all stay on the artist's computer so they can rest assured that their art isn't being pipelined directly into the next image model.

**2) It does real work -- anywhere you are.** Whether that's at your desktop or your phone, you can create line art and animation prototypes, all in the artist's style. This is because Yak has the ability to call image and video models that are on the computer -- including fine-tuned models specific to the artist. As a plus, Yak also has memory. So it can remember feedback you give it and how you like to describe your work.

**3) Yak can help the artist manage their broader workload as well.** Yak isn't limited to just image and art generation. It can have visibility into your calendar and email so that it has context into what's on your plate, and make proactive suggestions to help you manage your workload.

A special thank you to **NVIDIA** and **Hugging Face**. Yak's capability is unlocked by the power of the DGX Spark -- 128 GB of GPU memory allows for the LLM and image generation models to run at the same time on the device. Hugging Face has a powerful open source community of fine-tuned models that can easily be downloaded and run on the DGX Spark.

---

## What You Need

- **NVIDIA DGX Spark** or any Linux/Mac machine with an NVIDIA GPU and 16+ GB memory
- **Docker** (recommended) or Python 3.11+
- **Ollama** running locally

## Get Started (Docker)

This is the easiest path. The Docker image includes everything.

**1. Clone and configure**

```bash
git clone https://github.com/jeremiahoclark/OpenYak.git
cd OpenYak
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

Yak talks to you where you already work. Set up one or all of them.

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

Yak includes FLUX.2 Klein for image generation. You can create images and animate them into short videos.

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
