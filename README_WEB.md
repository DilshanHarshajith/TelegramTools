# TelegramTools Web UI

A modern, responsive web interface for TelegramTools built with Flask.

## Features

- 🎨 **Modern UI** - Beautiful glassmorphism design with smooth animations
- 📱 **Responsive** - Works on desktop, tablet, and mobile devices
- ⚡ **Real-time Progress** - Live updates during module execution via Server-Sent Events
- 🔧 **Dynamic Forms** - Auto-generated forms based on module arguments
- 📊 **Results Display** - Clear visualization of execution results and outputs

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API Credentials

Make sure your `.env` file contains your Telegram API credentials:

```env
API_ID=your_api_id
API_HASH=your_api_hash
```

### 3. Start the Web Server

```bash
python app.py
```

The web interface will be available at: **http://localhost:5000**

## Usage

### Accessing Modules

1. Open your browser and navigate to `http://localhost:5000`
2. You'll see a dashboard with all available modules
3. Click on any module card to access its configuration page

### Running a Module

1. Select a module from the dashboard
2. Fill in the required parameters in the form
3. Click "Run Module" to start execution
4. Monitor real-time progress updates
5. View results when execution completes

### Available Modules

- **Connector** - Analyze shared infrastructure between Telegram groups
- **Message Scraper** - Search and extract messages from groups
- **User Export** - Export user data and profile photos from groups
- **User Mapper** - Map and analyze user relationships
- **Origin Tracer** - Trace message origins and forwarding chains

## Form Field Types

The web UI automatically generates appropriate form fields based on module arguments:

- **Text inputs** - For strings and usernames
- **Number inputs** - For limits and counts
- **Checkboxes** - For boolean flags
- **Textareas** - For lists (groups, users, etc.)
- **Select dropdowns** - For choices

### List Inputs

For fields that accept multiple values (like `--groups`), you can enter values in two ways:

1. **One per line:**
   ```
   https://t.me/group1
   https://t.me/group2
   https://t.me/group3
   ```

2. **Comma-separated:**
   ```
   https://t.me/group1, https://t.me/group2, https://t.me/group3
   ```

## Output Files

All output files are saved to the same location as the CLI tool:
- `data/output/<module_name>/`

You can access these files directly from your file system after execution completes.

## Architecture

### Backend Components

- **`app.py`** - Main Flask application with routes and SSE streaming
- **`web_runner.py`** - Backend integration layer that wraps existing modules
- **`main.py`** - Original CLI tool (unchanged, used as backend)

### Frontend Components

- **Templates** (`templates/`)
  - `base.html` - Base template with navigation
  - `index.html` - Home page with module grid
  - `module.html` - Dynamic module configuration page
  - `results.html` - Execution results display
  - `error.html` - Error page

- **Static Assets** (`static/`)
  - `css/style.css` - Modern styling with glassmorphism
  - `js/main.js` - Utility functions
  - `js/module.js` - Form handling and SSE client

## How It Works

1. **Module Discovery** - On startup, the web app discovers all available modules from `modules/tasks/`
2. **Form Generation** - For each module, forms are dynamically generated based on the module's `get_args()` function
3. **Execution** - When a form is submitted:
   - Form data is converted to `argparse.Namespace`
   - Module runs in a background thread
   - Output is captured and streamed via SSE
4. **Results** - Execution results are displayed with formatted output and download links

## Troubleshooting

### Port Already in Use

If port 5000 is already in use, you can change it in `app.py`:

```python
app.run(debug=True, host='0.0.0.0', port=5001, threaded=True)
```

### Module Not Found

Make sure all modules are in the `modules/tasks/` directory and have a `get_args()` function.

### SSE Connection Issues

If real-time updates don't work, the app will automatically fall back to polling for status updates.

## Development

### Running in Debug Mode

The app runs in debug mode by default, which enables:
- Auto-reload on code changes
- Detailed error pages
- Template auto-reload

### Adding New Modules

New modules added to `modules/tasks/` will automatically appear in the web UI. No changes to the web app code are needed.

## CLI Tool Still Works

The original CLI tool (`main.py`) remains fully functional. You can use both the web UI and CLI interchangeably:

```bash
# CLI usage
python main.py -m message_scraper --keyword "test" --limit 100

# Web UI usage
python app.py
```

## Browser Compatibility

Tested and working on:
- Chrome/Chromium 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Security Notes

- The web server binds to `0.0.0.0` by default, making it accessible on your network
- For production use, consider:
  - Adding authentication
  - Using HTTPS
  - Restricting host binding to `127.0.0.1`
  - Setting up proper CORS policies

## Support

For issues or questions:
1. Check the console output for errors
2. Review the browser developer console
3. Check module-specific documentation in the main README

---

**Enjoy using TelegramTools Web UI! 🚀**
