# TelegramTools

A modular toolkit for Telegram automation, data scraping, and analysis built on the Telethon library.

## Features

- **Media Downloader** — Download photos, videos, audio, documents, voice messages, GIFs, and stickers from channels/groups. Concurrent downloads, resume support, date and type filtering.
- **Message Scraper** — Search and export messages by keyword or sender, with optional reply context.
- **User Export** — Extract unique users from a group/channel member list (with a fallback to message history when the member list is hidden) and download their profile photos.
- **Origin Tracer** — Trace the original source of forwarded messages, single or in bulk.
- **Info Dumper** — Deep-dive user profile dump: status, common chats, photos (JSON output).
- **Post Downloader** — Download profile stories/posts from a user's profile page.
- **Terminal Chat** — Interactive terminal-based chat client with chat list, history, and search.
- **Modular Design** — Every module is fully standalone. Drop any module anywhere and run it directly.

## Installation

```bash
git clone https://github.com/DilshanHarshajith/TelegramTools.git
cd TelegramTools
pip install -r requirements.txt
```

## Configuration

Get your `API_ID` and `API_HASH` from [my.telegram.org/apps](https://my.telegram.org/apps).

Credentials are resolved in this order — the first source that provides both wins:

1. `.env` file — searched in the script's directory, then `~/.env`, then the current working directory
2. Environment variables — `API_ID` and `API_HASH`
3. Interactive prompt — asked at runtime, with an option to save to `.env`

**Recommended:** create a `.env` file in the project root (or wherever you run from):

```env
API_ID=12345678
API_HASH=your_api_hash_here
```

`config.py` is optional. If present, all modules use it for credentials and settings. If absent, each module resolves credentials entirely on its own — no other project file is required.

---

## Module Reference

### media_downloader

Downloads media from channels and groups.

```
python media_downloader.py <groups...> [options]

groups                @username, t.me/link, invite link, numeric ID, or file path

Type filters (combine freely; default: all):
  -p, --photo         Photos
  -v, --video         Videos
  -d, --document      Documents
  -a, --audio         Audio files
  --voice             Voice messages
  --gif               GIFs / animations
  --sticker           Stickers

Options:
  -n, --limit N       Max files to download per group (default: 0 = all)
  -w, --workers N     Concurrent downloads (default: 4)
  --out DIR           Output directory
  --dry-run           Scan and count without downloading
  --no-resume         Re-download everything, ignore existing files
  --min-date DATE     Only media on or after YYYY-MM-DD [HH:MM:SS]
  --max-date DATE     Only media on or before YYYY-MM-DD [HH:MM:SS]
  --reverse           Scan from oldest messages first
  --hide-group        Mute and archive any group joined by the tool during the run
```

**Examples:**
```bash
python media_downloader.py @channel --video --photo
python media_downloader.py @channel -n 100 --dry-run
python media_downloader.py @channel --min-date 2024-01-01 --hide-group
python media_downloader.py groups.txt --audio --out ./downloads
```

---

### message_scraper

Search and export messages by keyword or sender.

```
python message_scraper.py [options]

  --groups            Group links/usernames or a file containing them
  -k, --keyword       Keyword(s) to match (any match includes the message)
  --user              Filter by sender ID or @username
  -l, --limit N       Max messages to scan per group (default: 0 = all)
  --replies           Include replies to matching messages in output
  -v, --verbose       Show sender and text snippet per match
  --out DIR           Output directory
```

**Examples:**
```bash
python message_scraper.py --groups @channel -k bitcoin
python message_scraper.py --groups @channel -k bitcoin scam --replies
python message_scraper.py --groups groups.txt --user @someone
```

---

### user_export

Export users from a group/channel member list (with a fallback to message history when the member list is hidden) and download profile photos.

```
python user_export.py <groups...> [options]

groups                Group links or a file containing groups

  --no-photos         Skip profile photo downloads (photos downloaded by default)
  --limit N           Max members/messages to fetch per group (default: 0 = all)
  -v, --verbose       Show usernames during scan
  --out DIR           Output directory
  --scan-messages     Skip the member list and scan message history (legacy mode)
```

**Examples:**
```bash
python user_export.py @group
python user_export.py @group --no-photos --limit 500
python user_export.py groups.txt --out ./results
python user_export.py @group --scan-messages
```

---

### origin_tracer

Trace the original source of forwarded messages.

```
python origin_tracer.py [options]

  --groups            Group/channel links or usernames
  --message-id N      Trace a single message by ID (single message mode)
  --limit N           Max messages to scan per group (bulk mode, default: 0 = all)
  --min-count N       Minimum forwards required to include a source in the report
  --out DIR           Output directory
```

**Examples:**
```bash
python origin_tracer.py --groups @channel
python origin_tracer.py --groups @channel --message-id 42
python origin_tracer.py --groups @channel --limit 1000 --min-count 3
```

---

### info

Dump comprehensive user information to JSON.

```
python info.py <users...> [options]

users                 Usernames, numeric IDs, phone numbers (+...), or file path

  --photos            Download all profile photos
  -o, --out DIR       Output directory
  -f, --filter KEYS   Only include these JSON keys in output
```

**Examples:**
```bash
python info.py @username
python info.py @username --photos --out ./results
python info.py users.txt -f id username status common_chats_count
```

---

### post_downloader

Download profile stories and posts from a user's profile page.

```
python post_downloader.py <usernames...> [options]

usernames             One or more @usernames

  -w, --workers N     Concurrent downloads (default: 4)
  --out DIR           Output directory
  --no-resume         Re-download everything, ignore existing files
```

**Examples:**
```bash
python post_downloader.py @username
python post_downloader.py @user1 @user2 --out ./stories
python post_downloader.py @username --no-resume -w 8
```

---

### #terminal_chat  *(interactive)*

Terminal-based chat client. Run directly — no arguments needed.

```
python '#terminal_chat.py'

Keybindings:
  s           Search by username, phone, or chat ID
  0           Return to main menu
  Esc         Exit current chat / return to menu
  /back       Exit current chat
  /refresh    Refresh chat history
```

---

## Project Structure

```
TelegramTools/
├── config.py              # Central config and credential resolution (optional)
├── media_downloader.py    # Standalone module
├── message_scraper.py     # Standalone module
├── user_export.py         # Standalone module
├── origin_tracer.py       # Standalone module
├── info.py                # Standalone module
├── post_downloader.py     # Standalone module
├── #terminal_chat.py      # Interactive standalone module
├── !Module_Template.py    # Template for new modules
└── data/
    ├── groups.txt         # Default group list (one per line)
    └── output/            # Generated results
```

> **Module prefixes:** `!` = template/excluded from discovery, `#` = interactive module.
