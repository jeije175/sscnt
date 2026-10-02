# SS.com → Telegram apartment monitor

Monitors:

https://www.ss.com/lv/real-estate/flats/riga/centre/hand_over/

Every 5 minutes, GitHub Actions checks the first page. When an unseen SS.com
listing ID appears, it sends a Telegram message to the configured group.

## What you need

- A GitHub account
- A Telegram bot
- A Telegram group where the bot is a member
- The group's numeric chat ID

## 1. Create the Telegram bot

In Telegram, open **@BotFather** and use `/newbot`.

Copy the bot token it gives you. Keep it secret.

## 2. Add the bot to your group

Create/open the Telegram group you want to receive notifications in and add
your new bot.

For the simplest setup, send at least one normal message in the group after
adding the bot.

## 3. Get the group chat ID

Open this URL in a browser, replacing `TOKEN` with your bot token:

https://api.telegram.org/botTOKEN/getUpdates

Find `"chat":{"id": ...}` for your group.

Group IDs normally look like `-1001234567890`.

If `getUpdates` is empty, send a new message in the group and refresh the URL.

## 4. Create a GitHub repository

Create a new repository, for example:

`sscom-telegram-monitor`

Upload:

- `monitor.py`
- `requirements.txt`
- `.github/workflows/monitor.yml`
- `state.json`

## 5. Add GitHub Secrets

Repository → Settings → Secrets and variables → Actions → New repository secret

Add:

`TELEGRAM_BOT_TOKEN` = your BotFather token

`TELEGRAM_CHAT_ID` = your group ID

Do NOT put either value into the source files.

## 6. Run it

Actions → **Monitor SS.com** → Run workflow.

The first run only records the listings currently on the page. It deliberately
does not send notifications for all existing listings.

After that, a newly appearing listing produces a Telegram message.

## Important

The monitor currently checks the first page only, which is normally exactly
what you want for "newest listings": SS.com puts the newest ads first.

The GitHub Actions schedule is nominally every 5 minutes, but GitHub can delay
scheduled jobs during busy periods. It is therefore not a guaranteed exact
5-minute notification system.

The monitor stores seen listing IDs in `state.json` and commits that file back
to the repository. Do not make the repository public if you do not want the
monitor history visible.

If SS.com changes its HTML structure, the parser may need a small update.
