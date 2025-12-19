# TelegramTools

A comprehensive toolkit for Telegram automation, data scraping, and analysis using the Telethon library. This project provides modular tools for scraping messages, exporting user data, resolving usernames, and analyzing infrastructure overlap between groups.

## Features

-   **Message Scraper**: Search and export messages from groups based on keywords, with options to include replies and filter by user.
-   **User Export**: Scrape user members from groups and download high-quality profile photos.
-   **User Mapper**: Bulk resolve usernames to user IDs and detailed entity information.
-   **Infrastructure Hunter**: Analyze and detect shared infrastructure (domains, users, bots) across multiple channels to find overlaps.
-   **Modular Design**: Easy to extend with new task modules.

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
    -   Go to [my.telegram.org](https://my.telegram.org).
    -   Log in and create a new application to get your `API_ID` and `API_HASH`.

2.  **Set up Environment Variables**:
    -   Create a `.env` file in the project root (or rename `.env.example` if available).
    -   Add your credentials:
        ```env
        API_ID=12345678
        API_HASH=your_api_hash_here
        ```

## Usage

The toolkit uses a central entry point `main.py`. You can run specific modules using the `-m` flag.

### List Available Modules
To see all available task modules:
```bash
python main.py --list-modules
```

### 1. Message Scraper (`message_scraper`)
Search for messages containing specific keywords in one or more groups.

**Arguments:**
-   `-k`, `--keyword` (Required): Keyword to search for.
-   `--groups`: List of group links/usernames or a file containing them.
-   `--limit`: Max messages to scan per group (default: 0 = all).
-   `--user`: Filter by sender ID or username.
-   `--replies`: Include replies to matching messages in the output.
-   `-v`: Verbose output.

**Example:**
```bash
python main.py -m message_scraper --groups @group1 @group2 -k "password" --limit 1000 -v
```

### 2. User Export (`user_export`)
Extract user lists from groups and download profile photos.

**Arguments:**
-   `--groups`: List of groups to scan.
-   `--users`: Inline list of user IDs or a file path to download photos for specific users (skips group scan).
-   `--no-photos`: Disable downloading profile photos.
-   `--limit`: Max messages to scan for finding users.

**Example (Scan group):**
```bash
python main.py -m user_export --groups https://t.me/example_chat --limit 500
```

**Example (Download specific user photos):**
```bash
python main.py -m user_export --users "123456789, 987654321"
```

### 3. User Mapper (`user_mapper`)
Resolve a list of usernames or IDs to their full Telegram entity details.

**Arguments:**
-   `--inputs`: List of usernames/IDs to resolve.
-   `--file`: File containing one username/ID per line.
-   `--output`: Custom path for the CSV output.

**Example:**
```bash
python main.py -m user_mapper --inputs @durov @telegram 1234567
```

### 4. Infrastructure Hunter (`connector`)
Analyze shared infrastructure (domains, users, bots) between multiple channels.

**Arguments:**
-   `--groups`: Two or more channels to compare.
-   `--min-user-overlap`: Minimum shared users to report.
-   `--min-domain-overlap`: Minimum shared domains to report.
-   `--export-graphml`: Export findings to a GraphML file.

**Example:**
```bash
python main.py -m connector --groups @channel_A @channel_B --min-user-overlap 5
```

## Project Structure

-   `main.py`: CLI entry point.
-   `config.py`: Configuration and environment variable loading.
-   `modules/tasks/`: individual task modules (`message_scraper.py`, `user_export.py`, etc.).
-   `data/`: Default directory for inputs and outputs.
    -   `data/output/`: Generated results (JSONs, CSVs, downloads).
