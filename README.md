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
- A reauth flow when the API key is revoked or expires

Not covered: anything that manages the integration's own credential (API
keys), browser Web Push subscriptions, invitations, or
family-lifecycle operations (create/delete a family, the kiosk dashboard key)
— those stay in the Chores app itself.

## Installation

Install via [HACS](https://hacs.xyz/):

1. Add this repository to HACS as a custom integration.
2. Install "Chores".
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Create Automation** and add the Chores integration.
5. Paste an API key (create one in the Chores app under **Settings → API keys**).

### API key permissions

Chores API keys carry their own permissions. Give the key the ones for what
you use:

| Permission | Needed for |
| --- | --- |
| Read | everything — the integration can't start without it |
| Tick off tasks | ticking chores off in the Must do / Can do lists |
| Manage tasks | the `create_task`, `update_task` and `delete_task` actions |
| Manage children | the `create_user` and `remove_child` actions |
| Payouts | the pay-out button and the `create_payout` action |

Family admin isn't used. An action the key lacks permission for fails with
an error naming the missing permission; everything else keeps working. A
key from before Chores had permissions still has all of them.

## Development

See [CLAUDE.md](CLAUDE.md) for development guidance and [ARCHITECTURE.md](ARCHITECTURE.md) for design details.

## Links

- [Chores web app](https://chores.apphub.casa)
- [Chores API documentation](https://buf.build/apphub/chores)
- [Home Assistant documentation](https://www.home-assistant.io/)
