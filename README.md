# Chores Home Assistant Integration

Home Assistant integration for [Chores](https://chores.apphub.casa), a household chore and allowance management service.

## Features

- Per-child todo list for today's chores; mark chores complete or incomplete from Home Assistant
- Per-child calendar of upcoming and past chores
- Balance and earnings sensors (today, this week, last 7 days, this/last month, totals, last payout)
- A pay-out button per child for the full outstanding balance
- Services for creating/updating/deleting tasks, creating a payout of a specific amount, adding a family member, and removing a child
- A `chores_task_completed` event for automations
- Multi-family support (add separate config entries for different households)
- Automatic token refresh flow

Not covered: anything that manages the integration's own credential (personal
access tokens), browser Web Push subscriptions, invitations, or
family-lifecycle operations (create/delete a family, the kiosk dashboard key)
— those stay in the Chores app itself.

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
