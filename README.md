# Chores Home Assistant Integration

Home Assistant integration for [Chores](https://chores.apphub.casa), a household chore and allowance management service.

## Features

- Per-child todo list for today's chores
- Mark chores complete or incomplete from Home Assistant
- Multi-family support (add separate config entries for different households)
- Automatic token refresh flow

## Installation

Install via [HACS](https://hacs.xyz/):

1. Add this repository to HACS as a custom integration.
2. Install "Chores".
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Create Automation** and add the Chores integration.
5. Paste your personal access token (create one in the Chores app under Settings).

## Development

See [CLAUDE.md](CLAUDE.md) for development guidance and [ARCHITECTURE.md](ARCHITECTURE.md) for design details.

## Links

- [Chores web app](https://chores.apphub.casa)
- [Chores API documentation](https://buf.build/apphub/chores)
- [Home Assistant documentation](https://www.home-assistant.io/)
