# TelegramTools

A comprehensive toolkit for Telegram automation, data scraping, and analysis using the Telethon library. This project provides modular tools for scraping messages, exporting user data, resolving usernames, tracing message origins, and analyzing infrastructure overlap between groups.

## Features

-   **Message Scraper**: Search and export messages from groups based on keywords, with options to include replies and filter by user. Now supports multiple keywords.
-   **Terminal Chat**: Interactive terminal-based chat client with recent chat list, message history, and search functionality. (CLI Only)
-   **User Export**: Scrape user members from groups and download high-quality profile photos.
-   **User Mapper**: Bulk resolve usernames to user IDs and detailed entity information.
-   **Origin Tracer**: Trace the original source of forwarded messages, either for a single message or in bulk across a group.
-   **Infrastructure Hunter**: Analyze and detect shared infrastructure (domains, users, bots) across multiple channels to find overlaps.
-   **Modular Design**: Easy to extend with new task modules. Supports interactive modules and module discovery filtering via prefixes (`!` to ignore, `#` to hide from Web UI).
-   **Web Interface**: A modern, responsive web UI for managing and running tasks.

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

2.  **Set up Credentials**:
    -   **Web UI (Recommended)**: Start the web server and use the built-in setup page to enter your credentials.
    -   **Manual**: Create a `.env` file in the project root and add:
        ```env
        API_ID=12345678
        API_HASH=your_api_hash_here
        ```

## Web Interface

A modern, responsive web interface for TelegramTools built with Flask.

### Features
- 🎨 **Modern UI** - Beautiful glassmorphism design with smooth animations
- 📱 **Responsive** - Works on desktop, tablet, and mobile devices
- ⚡ **Real-time Progress** - Live updates during module execution via Server-Sent Events
- 🔧 **Dynamic Forms** - Auto-generated forms based on module arguments
- 📊 **Results Display** - Clear visualization of execution results and outputs
- 📂 **Data Browser** - Browse and download results directly from the UI

### Quick Start
Run the web server:
```bash
python WEB/app.py
```
The web interface will be available at: **http://localhost:5000**

### Usage
1. Open your browser and navigate to `http://localhost:5000`
2. If it's your first time, you'll be redirected to the **Setup** page to enter your API credentials.
3. Select a module from the dashboard.
4. Fill in the required parameters (forms are auto-generated).
5. Click "Run Module" and monitor real-time progress.
6. View results and download output files via the results page or the **Data Browser**.

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
-   `-k`, `--keyword` (Required): Keyword(s) to search for.
-   `--groups`: List of group links/usernames or a file containing them.
-   `--limit`: Max messages to scan per group (default: 0 = all).
-   `--user`: Filter by sender ID or username.
-   `--replies`: Include replies to matching messages in the output.
-   `-v`: Verbose output.

### 2. User Export (`user_export`)
Extract user lists from groups and download profile photos.

**Arguments:**
-   `--groups`: List of groups to scan.
-   `--users`: Inline list of user IDs or a file path to download photos for specific users (skips group scan).
-   `--no-photos`: Disable downloading profile photos.
-   `--limit`: Max messages to scan for finding users.

### 3. User Mapper (`user_mapper`)
Resolve a list of usernames or IDs to their full Telegram entity details.

**Arguments:**
-   `--inputs`: List of usernames/IDs to resolve.
-   `--file`: File containing one username/ID per line.
-   `--output`: Custom path for the CSV output.

### 4. Origin Tracer (`origin_tracer`)
Trace the original source of forwarded messages.

**Arguments:**
-   `--groups`: Telegram group/channel links or usernames to analyze.
-   `--message-id`: Specific Message ID to trace origin for (Single Message Mode).
-   `--limit`: Maximum messages to scan per group (Bulk Mode).
-   `--min-count`: Minimum forwards required to report a source (Bulk Mode).

### 5. Infrastructure Hunter (`connector`)
Analyze shared infrastructure (domains, users, bots) between multiple channels.

**Arguments:**
-   `--groups`: Two or more channels to compare.
-   `--min-user-overlap`: Minimum shared users to report.
-   `--min-domain-overlap`: Minimum shared domains to report.
-   `--export-graphml`: Export findings to a GraphML file.
-   `-v`: Verbose output.

### 6. Terminal Chat (`#terminal_chat`)
An interactive terminal-based chat client. Note: This module is intended for CLI use only and is hidden from the Web UI.

**Arguments:**
-   `--limit`: Number of recent chats to display in the list (default: 20).
-   `s`: Search for a contact or group by username, phone number, or Chat ID.
-   `0`: Return to the main menu.
-   `Esc`: Exit the current chat or return to the main menu.
-   `/back`: Exit the current chat.
-   `/refresh`: Refresh the current chat history.

## Interactive Mode

If you run `main.py` without any arguments, it enters an **Interactive Mode**:
```bash
python main.py
```
This mode provides a menu-driven interface to select and configure modules. For standard modules, it will prompt you for arguments after selection. For interactive modules like `#terminal_chat`, it will skip the argument prompt and start immediately.

## Project Structure

-   `main.py`: CLI entry point.
-   `config.py`: Configuration and environment variable loading.
-   `modules/`: 
    -   `modules/tasks/`: Individual task modules (`message_scraper.py`, `user_export.py`, `origin_tracer.py`, etc.).
    -   `modules/utils/`: Shared utilities (auth, output, group handling).
-   `WEB/`: Flask Web UI.
    -   `WEB/app.py`: Web interface entry point.
    -   `WEB/web_runner.py`: Backend integration for Web UI.
    -   `WEB/templates/`: HTML templates.
    -   `WEB/static/`: CSS and JS assets.
-   `data/`: Default directory for inputs and outputs.
    -   `data/output/`: Generated results (JSONs, CSVs, downloads).
