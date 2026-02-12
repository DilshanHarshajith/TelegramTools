# TelegramTools

A comprehensive toolkit for Telegram automation, data scraping, and analysis using the Telethon library. This project provides modular tools for scraping messages, exporting user data, resolving usernames, tracing message origins, and analyzing infrastructure overlap between groups.

## Features

- **Message Scraper**: Search and export messages from groups based on keywords, with options to include replies and filter by user. Now supports multiple keywords.
- **Terminal Chat**: Interactive terminal-based chat client with recent chat list, message history, and search functionality. (CLI Only)
- **User Export**: Scrape user members from groups and download high-quality profile photos.
- **User Mapper**: Bulk resolve usernames to user IDs and detailed entity information.
- **Origin Tracer**: Trace the original source of forwarded messages, either for a single message or in bulk across a group.
- **Info Dumper**: Deep dive into user profiles, status, and history (JSON dump + photos).
- **Find Account**: Lookup Telegram account details by phone number.
- **Modular Design**: Easy to extend with new task modules. Supports interactive modules and module discovery filtering via prefixes (`!` to ignore).

## Installation

1.  **Clone the repository**:

    ```bash
    git clone https://github.com/DilshanHarshajith/TelegramTools.git
    cd TelegramTools
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

1.  **Obtain API Credentials**:
    - Go to [my.telegram.org](https://my.telegram.org).
    - Log in and create a new application to get your `API_ID` and `API_HASH`.

2.  **Set up Credentials**:
    - Create a `.env` file in the project root and add:
      ```env
      API_ID=12345678
      API_HASH=your_api_hash_here
      ```

## CLI Usage

The toolkit uses a central entry point `main.py`. You can run specific modules using the `-m` flag.

### List Available Modules

To see all available task modules:

```bash
python main.py --list-modules
```

### 1. Message Scraper (`message_scraper`)

Search for messages containing specific keywords in one or more groups.

**Arguments:**

- `-k`, `--keyword`: Keyword(s) to search for. Required unless `--user` is provided.
- `--groups`: List of group links/usernames or a file containing them.
- `-l`, `--limit`: Max messages to scan per group (default: 0 = all).
- `--user`: Filter by sender ID or username. Required unless `--keyword` is provided.
- `--replies`: Include replies to matching messages in the output.
- `-v`, `--verbose`: Verbose output (show matching snippets).
- `--out`: Output directory.

### 2. User Export (`user_export`)

Extract user lists from groups and download profile photos.

**Arguments:**

- `groups` (Positional): List of group links or a file containing groups.
- `--no-photos`: Disable downloading profile photos.
- `--limit`: Max messages to scan for finding users.
- `-v`, `--verbose`: Show usernames during scan.
- `--out`: Output directory.

### 3. User Mapper (`user_mapper`)

Resolve a list of usernames or IDs to their full Telegram entity details.

**Arguments:**

- `--inputs`: List of usernames/IDs to resolve.
- `--file`: File containing one username/ID per line.
- `--output`: Custom filename for the CSV output.
- `--photo`: Download user photos.
- `--out`: Output directory.

### 4. Origin Tracer (`origin_tracer`)

Trace the original source of forwarded messages.

**Arguments:**

- `--groups`: Telegram group/channel links or usernames to analyze.
- `--message-id`: Specific Message ID to trace origin for (Single Message Mode).
- `--limit`: Maximum messages to scan per group (Bulk Mode).
- `--min-count`: Minimum forwards required to report a source (Bulk Mode).
- `--out`: Output directory.

### 5. Info Dumper (`info`)

Dump comprehensive user information and download profile photos.

**Arguments:**

- `users` (Required): Usernames, IDs, Phone numbers (starting with +), or file path containing them.
- `--photos`: Download all profile photos.
- `-o`, `--out`: Output directory (default: data/output/info).

### 6. Terminal Chat (`#terminal_chat`)

An interactive terminal-based chat client. Note: This module is intended for CLI use only.

**Arguments:**

- `--limit`: Number of recent chats to display in the list (default: 20).
- `s`: Search for a contact or group by username, phone number, or Chat ID.
- `0`: Return to the main menu.
- `Esc`: Exit the current chat or return to the main menu.
- `/back`: Exit the current chat.
- `/refresh`: Refresh the current chat history.

### 7. Find Account (`num_to_acc`)

Lookup a Telegram account by phone number.

**Arguments:**

- `inputs` (Required): Phone number(s) to search (including country code) or file path(s).
- `-o`, `--out`: Output JSON file path.

## Interactive Mode

If you run `main.py` without any arguments, it enters an **Interactive Mode**:

```bash
python main.py
```

This mode provides a menu-driven interface to select and configure modules. For standard modules, it will prompt you for arguments after selection. For interactive modules like `#terminal_chat`, it will skip the argument prompt and start immediately.

## Project Structure

- `main.py`: CLI entry point.
- `config.py`: Configuration and environment variable loading.
- `modules/`:
  - `modules/tasks/`: Individual task modules (`message_scraper.py`, `user_export.py`, `origin_tracer.py`, etc.).
  - `modules/utils/`: Shared utilities (auth, output, group handling).

- `data/`: Default directory for inputs and outputs.
  - `data/output/`: Generated results (JSONs, CSVs, downloads).
