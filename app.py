"""
Flask Web UI for TelegramTools
Main application entry point
"""
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, redirect, url_for, send_from_directory
import os
import sys
import json
import time
import tempfile
from werkzeug.utils import secure_filename
import dotenv

# Load env variables first
dotenv.load_dotenv()

# Check for required credentials before importing config via web_runner
SETUP_REQUIRED = False
if not os.getenv("API_ID") or not os.getenv("API_HASH"):
    # Inject dummy values to prevent config.py from exiting
    os.environ["API_ID"] = "12345" 
    os.environ["API_HASH"] = "dummy_hash_for_startup"
    SETUP_REQUIRED = True

from web_runner import executor
import config

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['TEMPLATES_AUTO_RELOAD'] = True


@app.before_request
def check_setup():
    """Check if setup is required and redirect if necessary."""
    global SETUP_REQUIRED
    
    # Allow static resources and setup page
    if request.path.startswith('/static') or request.path == '/setup':
        return
        
    if SETUP_REQUIRED:
        return redirect(url_for('setup'))


@app.route('/setup', methods=['GET', 'POST'])
def setup():
    """Handle initial setup of API credentials."""
    global SETUP_REQUIRED
    
    if request.method == 'POST':
        api_id = request.form.get('api_id')
        api_hash = request.form.get('api_hash')
        
        if api_id and api_hash:
            # Write to .env file
            env_path = os.path.join(os.path.dirname(__file__), '.env')
            with open(env_path, 'a') as f:
                f.write(f"\nAPI_ID={api_id}\n")
                f.write(f"\nAPI_HASH={api_hash}\n")
            
            # Update environment variables
            os.environ['API_ID'] = api_id
            os.environ['API_HASH'] = api_hash
            
            # Update config module values
            config.API_ID = api_id
            config.API_HASH = api_hash
            
            # Update global flag
            SETUP_REQUIRED = False
            
            return redirect(url_for('index'))
            
    return render_template('setup.html')


@app.route('/')
def index():
    """Home page with module list."""
    modules = executor.get_modules()
    module_info = []
    
    for name, module in sorted(modules.items()):
        # Get module docstring or description
        description = ''
        if hasattr(module, '__doc__') and module.__doc__:
            description = module.__doc__.strip().split('\n')[0]
        
        module_info.append({
            'name': name,
            'description': description,
            'url': f'/module/{name}'
        })
    
    return render_template('index.html', modules=module_info)


@app.route('/dashboard')
def dashboard():
    """Dashboard showing all running and completed tasks."""
    all_tasks = executor.get_all_tasks()
    return render_template('dashboard.html', tasks=all_tasks)


@app.route('/module/<module_name>')
def module_page(module_name):
    """Display module page with form."""
    modules = executor.get_modules()
    
    if module_name not in modules:
        return render_template('error.html', 
                             error=f"Module '{module_name}' not found"), 404
    
    # Get argument specifications for form generation
    args_spec = executor.get_module_args_spec(module_name)
    
    # Get module description
    module = modules[module_name]
    description = ''
    if hasattr(module, '__doc__') and module.__doc__:
        description = module.__doc__.strip()
    
    return render_template('module.html',
                         module_name=module_name,
                         description=description,
                         args_spec=args_spec)


@app.route('/api/execute/<module_name>', methods=['POST'])
def execute_module(module_name):
    """Execute a module with provided parameters."""
    try:
        # Check if request has files
        if request.files:
            # Handle multipart/form-data with files
            form_data = {}
            
            # Get regular form fields
            for key in request.form:
                value = request.form[key]
                # Handle checkboxes
                if value.lower() in ['true', 'false']:
                    form_data[key] = value.lower() == 'true'
                else:
                    form_data[key] = value
            
            # Handle file uploads
            upload_dir = tempfile.mkdtemp(prefix='telegram_tools_')
            for key in request.files:
                file = request.files[key]
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(upload_dir, filename)
                    file.save(filepath)
                    form_data[key] = filepath
        else:
            # Handle JSON data (no files)
            form_data = request.get_json() or {}
        
        # Convert form data types
        processed_data = {}
        for key, value in form_data.items():
            # Handle checkboxes
            if isinstance(value, bool):
                processed_data[key] = value
            # Handle numbers
            elif key in ['limit', 'max_messages_per_chat', 'min_domain_overlap', 'min_user_overlap']:
                try:
                    processed_data[key] = int(value) if value else 0
                except (ValueError, TypeError):
                    processed_data[key] = 0
            else:
                processed_data[key] = value
        
        # Start execution
        task_id = executor.start_module_execution(module_name, processed_data)
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f'Started execution of {module_name}'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/status/<task_id>')
def task_status(task_id):
    """Get status of a running task."""
    status = executor.get_task_status(task_id)
    
    if status is None:
        return jsonify({'error': 'Task not found'}), 404
    
    return jsonify(status)


@app.route('/api/stream/<task_id>')
def stream_task(task_id):
    """Stream task progress using Server-Sent Events."""
    def generate():
        """Generate SSE events for task progress."""
        max_iterations = 300  # 5 minutes max (300 * 1 second)
        iteration = 0
        
        while iteration < max_iterations:
            status = executor.get_task_status(task_id)
            
            if status is None:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Task not found'})}\n\n"
                break
            
            # Send any new messages
            for msg in status.get('messages', []):
                yield f"data: {json.dumps(msg)}\n\n"
            
            # Check if task is complete
            if status['status'] in ['complete', 'error']:
                yield f"data: {json.dumps({'type': 'done', 'status': status['status']})}\n\n"
                break
            
            # Send heartbeat
            if iteration % 5 == 0:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            
            time.sleep(1)
            iteration += 1
        
        # Timeout
        if iteration >= max_iterations:
            yield f"data: {json.dumps({'type': 'timeout', 'message': 'Task execution timeout'})}\n\n"
    
    return Response(stream_with_context(generate()), 
                   mimetype='text/event-stream',
                   headers={
                       'Cache-Control': 'no-cache',
                       'X-Accel-Buffering': 'no'
                   })


@app.route('/results/<task_id>')
def results_page(task_id):
    """Display results of completed task."""
    status = executor.get_task_status(task_id)
    
    if status is None:
        return render_template('error.html', 
                             error='Task not found'), 404
    
    return render_template('results.html',
                         task_id=task_id,
                         module_name=status['module'],
                         status=status)


@app.route('/data')
@app.route('/data/<path:subpath>')
def data_browser(subpath=""):
    """Browse the output directory."""
    base_dir = os.path.abspath(config.OUTPUT_DIR)
    current_dir = os.path.abspath(os.path.join(base_dir, subpath))
    
    # Security check: ensure current_dir is within base_dir
    if not current_dir.startswith(base_dir):
        return render_template('error.html', error="Access denied"), 403
    
    if not os.path.exists(current_dir):
        return render_template('error.html', error="Directory not found"), 404
    
    items = []
    for item in sorted(os.listdir(current_dir)):
        item_path = os.path.join(current_dir, item)
        rel_path = os.path.relpath(item_path, base_dir)
        
        is_dir = os.path.isdir(item_path)
        size = os.path.getsize(item_path) if not is_dir else 0
        
        items.append({
            'name': item,
            'rel_path': rel_path,
            'is_dir': is_dir,
            'size': size,
            'modified': time.ctime(os.path.getmtime(item_path))
        })
    
    # Calculate breadcrumbs
    breadcrumbs = []
    parts = subpath.split('/') if subpath else []
    curr_path = ""
    for part in parts:
        if not part: continue
        curr_path = os.path.join(curr_path, part)
        breadcrumbs.append({'name': part, 'path': curr_path})
        
    return render_template('data_browser.html', 
                         items=items, 
                         subpath=subpath, 
                         breadcrumbs=breadcrumbs)


@app.route('/download/<path:filepath>')
def download_file(filepath):
    """Download a file from the output directory."""
    base_dir = os.path.abspath(config.OUTPUT_DIR)
    file_path = os.path.abspath(os.path.join(base_dir, filepath))
    
    # Security check: ensure file_path is within base_dir
    if not file_path.startswith(base_dir):
        return jsonify({'error': 'Access denied'}), 403
        
    if not os.path.exists(file_path) or os.path.isdir(file_path):
        return jsonify({'error': 'File not found'}), 404
        
    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    
    return send_from_directory(directory, filename, as_attachment=True)


@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', error='Page not found'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', error='Internal server error'), 500


if __name__ == '__main__':
    print("=" * 60)
    print("TelegramTools Web UI")
    print("=" * 60)
    print(f"Available modules: {', '.join(sorted(executor.get_modules().keys()))}")
    print("\nStarting Flask server...")
    print("Access the web UI at: http://localhost:5000")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
