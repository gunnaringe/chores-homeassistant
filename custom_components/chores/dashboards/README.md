# Example Dashboards

This directory contains example Lovelace dashboards for the Chores integration.

## Installing the Example Dashboard

### Option 1: Copy and Edit (Recommended)

1. Copy `chores.yaml` to your Home Assistant config directory:
   ```bash
   cp chores.yaml /path/to/config/dashboards/
   ```

2. In Home Assistant, go to **Settings → Dashboards → Create Dashboard** and select **Load from YAML**.

3. Choose the dashboard file and customize as needed:
   - Replace `todo.lisa`, `todo.emma`, etc. with the actual entity IDs of your children
   - Adjust card types and layout to suit your preferences
   - Add sensors, buttons, and other entities as new Chores integration features roll out

### Option 2: Manual Reproduction

Use the cards and layout in `chores.yaml` as a reference and build your dashboard visually in the Home Assistant UI.

## Current Features

- **Today's Chores** — Todo lists per child
  - Check off completed chores
  - Shows mandatory vs. optional tasks
  - Live sync with Chores app

- **Balances Section** (placeholder)
  - Ready for balance sensors when they ship
  - Template includes sensor entities for quick addition

- **History Section** (placeholder)
  - Ready for monthly earnings and payouts
  - Includes example automation for task completion notifications

## Future Enhancements

As new Chores integration features are added, replace the placeholder cards with:

- **Sensors**: Child balance, earned today/week/month
- **Services**: Payout full balance or custom amount
- **Calendar**: View chores over a date range
- **Events**: Automations triggered on task completion

## Customization

The dashboard uses standard Lovelace cards:

- `todo-list` — from the Chores integration
- `entity` — from Home Assistant core
- `heading` — from Home Assistant core
- `markdown` — from Home Assistant core
- `custom:stack-in-card` — (optional, requires HACS card-mod or stack-in-card)

To remove the `custom:stack-in-card` requirement, replace it with multiple rows of regular cards.

## Entity ID Mapping

Update these to match your family's actual child entity IDs:

- `todo.lisa` → your first child's todo list
- `todo.emma` → your second child's todo list
- `todo.magnus` → your third child's todo list

Find the correct entity IDs in Home Assistant at **Settings → Devices & Services → Chores**.
