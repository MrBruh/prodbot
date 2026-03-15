# Phase 2 — Manual Test Checklist

Run the bot with `venv/Scripts/python bot.py` and test in your Discord server.

## Pre-flight
- [ ] Bot comes online and shows as green in the member list
- [ ] Terminal prints `Logged in as <BotName>`
- [ ] No errors in terminal on startup

## Links (`cogs/links.py`)

- [ ] `!save https://github.com` — saves link, embed shows URL + Claude-generated title
- [ ] `!save https://example.com #test #demo` — saves with tags shown in embed
- [ ] `!links` — shows the two unread links just saved
- [ ] `!read 1` — responds "Link #1 marked as read."
- [ ] `!links` — now only shows 1 unread link
- [ ] `!links read` — shows the 1 read link
- [ ] `!links all` — shows both links
- [ ] `!read 999` — responds "No link found with ID 999."

## Todos (`cogs/todos.py`)

- [ ] `!todo add Write unit tests` — responds "Added: **Write unit tests**"
- [ ] `!todo add Review pull request` — adds second task
- [ ] `!todo` — shows today's tasks in a code block, progress 0/2 (0%)
- [ ] `!today` — same output as `!todo`
- [ ] `!todo done 1` — responds "Task #1 marked as done!"
- [ ] `!todo` — shows progress 1/2 (50%), task 1 marked [done]
- [ ] `!todo done 999` — responds "No task found with ID 999."
- [ ] `!todo date 2020-01-01` — responds "No tasks for 2020-01-01."

## Bucket List (`cogs/bucket_list.py`)

- [ ] `!goal add Run a marathon #health` — responds "Goal added: **Run a marathon** [health]"
- [ ] `!goal add Learn Japanese #education` — adds with education category
- [ ] `!goal add Buy a house` — defaults to [general] category
- [ ] `!goals` — shows all goals grouped by category (Health, Education, General)
- [ ] `!goal` — same output as `!goals`
- [ ] `!goal progress 1` — responds "Goal #1 marked as in-progress."
- [ ] `!goals` — goal 1 now shows [~] instead of [ ]
- [ ] `!goal done 1` — responds "Goal #1 completed!"
- [ ] `!goals` — goal 1 now shows [x]
- [ ] `!goal done 999` — responds "No goal found with ID 999."

## Journal (`cogs/journal.py`)

- [ ] `!log Worked on the Discord bot all morning` — responds "Logged for today."
- [ ] `!log Fixed a tricky database bug after lunch` — adds second entry
- [ ] `!journal` — shows both entries for today with timestamps
- [ ] `!journal 2020-01-01` — responds "No journal entries for 2020-01-01."
- [ ] `!reflect` — Claude generates a reflection based on today's todos + journal (requires ANTHROPIC_API_KEY set)

## Embed Formatting
- [ ] Link embeds have green color
- [ ] Todo embeds have gold color with progress footer
- [ ] Bucket list embeds have purple color
- [ ] Journal embeds have teal color
- [ ] Reflection embeds have orange color

## Error Handling
- [ ] Sending `!save` with no URL — bot shows usage error (discord.py default)
- [ ] Sending `!todo done abc` — bot shows conversion error (expected int)
- [ ] Bot stays online after any error (doesn't crash)
