"""
Backend integration layer for Flask web UI.
Wraps the existing TelegramTools modules for web execution.
"""
import asyncio
import argparse
import threading
import queue
import sys
import io
import re
from typing import Dict, Any, Optional, List
from contextlib import redirect_stdout, redirect_stderr
import os
import sys

# Add parent directory to path for root module imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import TelegramToolsApp
import config
import modules.utils.auth as auth
from telethon import TelegramClient

# Monkeypatch auth.get_client to use dynamic credentials
# This is necessary because 'from config import API_ID' in auth.py captures the initial (dummy) values
def patched_get_client():
    """Create and return a Telegram client instance with fresh credentials."""
    # Always read fresh from os.environ or config module
    api_id = os.getenv("API_ID") or config.API_ID
    api_hash = os.getenv("API_HASH") or config.API_HASH
    session_name = config.SESSION_NAME
    
    # Ensure they are valid strings/ints
    if api_id:
        try:
            api_id = int(api_id)
        except ValueError:
            pass
            
    return TelegramClient(session_name, api_id, api_hash)

# Apply patch
auth.get_client = patched_get_client



def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape sequences and OSC hyperlinks from text."""
    # Remove OSC 8 hyperlink sequences (8;id=NUMBER;file://PATH8;;)
    text = re.sub(r'8;id=\d+;[^8]*8;;', '', text)
    
    # Remove any remaining ]8; patterns (partial OSC codes)
    text = re.sub(r'\]8;[^;]*;[^\]]*', '', text)
    
    # Remove standalone ]8;; terminators
    text = re.sub(r'\]8;;', '', text)
    
    # Remove ANSI color codes and formatting
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', text)
    
    # Remove any remaining escape-like patterns
    text = re.sub(r'\x1B\]8;[^\x07\x1B]*(?:\x07|\x1B\\)', '', text)
    
    # Remove \r (carriage return) which tqdm uses to overwrite lines
    # We want to keep only the text after the last \r on a line, or just strip them
    text = text.replace('\r', '\n')
    
    # Clean up trailing colons and extra spaces left from removed sequences
    text = re.sub(r':\s*$', '', text, flags=re.MULTILINE)
    
    # Remove excessive blank lines
    text = re.sub(r'\n\s*\n', '\n', text)
    
    return text


class QueueWriter(io.StringIO):
    """
    A file-like object that writes to a queue.
    Used to capture stdout/stderr and stream it in real-time.
    """
    def __init__(self, q: queue.Queue, msg_type: str = 'log'):
        super().__init__()
        self.q = q
        self.msg_type = msg_type

    def write(self, s):
        if s:
            # Strip ANSI codes before putting in queue
            clean_s = strip_ansi_codes(s)
            if clean_s.strip():
                self.q.put({
                    'type': self.msg_type,
                    'message': clean_s
                })
        return super().write(s)


class ModuleExecutor:
    """Handles async execution of TelegramTools modules in background threads."""
    
    def __init__(self):
        self.app = TelegramToolsApp()
        self.app.discover_modules()
        self.running_tasks: Dict[str, Dict[str, Any]] = {}
        
    def get_modules(self) -> Dict[str, Any]:
        """Return discovered modules, filtering those meant for CLI only."""
        return {name: mod for name, mod in self.app.modules.items() 
                if not any(name.startswith(prefix) for prefix in config.WEB_IGNORE)}
    
    def get_module_args_spec(self, module_name: str) -> List[Dict[str, Any]]:
        """
        Extract argument specifications from a module's get_args function.
        Returns a list of argument definitions for form generation.
        """
        module = self.app.modules.get(module_name)
        if not module or not hasattr(module, 'get_args'):
            return []
        
        # Create a temporary parser to extract argument definitions
        parser = argparse.ArgumentParser()
        module.get_args(parser)
        
        args_spec = []
        for action in parser._actions:
            # Skip help action
            if action.dest == 'help':
                continue
                
            arg_info = {
                'dest': action.dest,
                'flags': action.option_strings,
                'type': self._get_arg_type(action),
                'default': action.default,
                'help': action.help or '',
                'required': action.required if hasattr(action, 'required') else False,
                'choices': action.choices,
                'nargs': action.nargs,
            }
            
            # Determine if it's a boolean flag
            if isinstance(action, argparse._StoreTrueAction) or isinstance(action, argparse._StoreFalseAction):
                arg_info['type'] = 'boolean'
                arg_info['action'] = 'store_true' if isinstance(action, argparse._StoreTrueAction) else 'store_false'
            
            args_spec.append(arg_info)
        
        return args_spec
    
    def _get_arg_type(self, action) -> str:
        """Determine the argument type for form field generation."""
        # Check if it's a file input based on dest name
        if action.dest == 'file' or 'file' in action.dest.lower():
            return 'file'
        elif action.nargs in ['+', '*']:
            # Arguments that accept multiple values
            return 'list'
        elif action.type == int:
            return 'number'
        elif action.type == str or action.type is None:
            return 'text'
        else:
            return 'text'
    
    def create_args_namespace(self, module_name: str, form_data: Dict[str, Any]) -> argparse.Namespace:
        """
        Convert web form data to argparse.Namespace object.
        """
        module = self.app.modules.get(module_name)
        if not module:
            raise ValueError(f"Module {module_name} not found")
        
        # Create parser to inspect actions/defaults
        parser = self.app.get_module_parser(module_name, module)
        
        # Manually construct Namespace from defaults instead of parsing empty args
        # This avoids erroring on required arguments which are missing from []
        args = argparse.Namespace()
        
        for action in parser._actions:
            if action.dest != argparse.SUPPRESS:
                # Use default value if available
                # For store_true/false, default is usually False/True
                # For others, it might be None or a specific value
                if hasattr(action, 'default'):
                    setattr(args, action.dest, action.default)
        
        # Get action info for proper type handling
        actions_by_dest = {action.dest: action for action in parser._actions}
        
        # Override with form data
        for key, value in form_data.items():
            if value is not None and value != '':
                action = actions_by_dest.get(key)
                
                # Check if this argument expects a list (nargs='+', '*', etc.)
                if action and action.nargs in ['+', '*']:
                    # Start with existing list if any (though default is usually None or [])
                    current_list = getattr(args, key, []) or []
                    if not isinstance(current_list, list):
                        current_list = []
                    
                    new_items = []
                    # Convert string to list if needed
                    if isinstance(value, str):
                        # Split by commas, newlines, or spaces
                        new_items = [v.strip() for v in value.replace(',', '\n').split('\n') if v.strip()]
                    elif isinstance(value, list):
                        new_items = value
                    else:
                        new_items = [value]
                    
                    # Extend unique items
                    # Only extend if we haven't already populated it from previous form field
                    # (e.g. if form sends multiple values for same key, though normally it sends one list)
                    # For safety, let's just assign if it was empty default, or append?
                    # Re-assignment is safer for the "initial load" from form data
                    if not current_list:
                         current_list = new_items
                    else:
                         current_list.extend(new_items)
                         
                    setattr(args, key, current_list)
                else:
                    setattr(args, key, value)

        # Process file uploads for list arguments (e.g. groups_file)
        for key in list(form_data.keys()):
            if key.endswith('_file'):
                base_key = key[:-5]
                action = actions_by_dest.get(base_key)
                
                if action and action.nargs in ['+', '*']:
                    file_path = form_data[key]
                    if file_path and os.path.isfile(file_path):
                        try:
                            # Generic file reading
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                            
                            # Parse content same as text input (newlines, commas)
                            file_items = [v.strip() for v in content.replace(',', '\n').split('\n') if v.strip()]
                            
                            # Merge with existing
                            current_list = getattr(args, base_key, []) or []
                            if not isinstance(current_list, list):
                                current_list = []
                                
                            current_list.extend(file_items)
                            setattr(args, base_key, current_list)
                        except Exception as e:
                            print(f"Error reading file {file_path}: {e}")
        
        # Process common args (like groups file handling)
        self.app.process_common_args(args)
        
        return args
    
    def execute_module(self, task_id: str, module_name: str, args: argparse.Namespace, 
                      output_queue: queue.Queue) -> None:
        """
        Execute a module in a background thread with real-time output capture.
        """
        # Capture stdout and stderr with real-time queue streaming
        stdout_writer = QueueWriter(output_queue, 'stdout')
        stderr_writer = QueueWriter(output_queue, 'stderr')
        
        try:
            output_queue.put({'type': 'status', 'message': f'Starting {module_name}...'})
            
            # Run the async module in a new event loop
            with redirect_stdout(stdout_writer), redirect_stderr(stderr_writer):
                asyncio.run(self.app.run_module(module_name, args))
            
            # Get the full contents for the final 'complete' message
            stdout_text = strip_ansi_codes(stdout_writer.getvalue())
            stderr_text = strip_ansi_codes(stderr_writer.getvalue())
            
            output_queue.put({
                'type': 'complete',
                'stdout': stdout_text,
                'stderr': stderr_text,
                'success': True
            })
            
        except Exception as e:
            output_queue.put({
                'type': 'error',
                'message': str(e),
                'stdout': strip_ansi_codes(stdout_writer.getvalue()),
                'stderr': strip_ansi_codes(stderr_writer.getvalue())
            })
    
    def start_module_execution(self, module_name: str, form_data: Dict[str, Any]) -> str:
        """
        Start module execution in background thread.
        Returns task_id for tracking.
        """
        import uuid
        task_id = str(uuid.uuid4())
        
        # Create args namespace
        args = self.create_args_namespace(module_name, form_data)
        
        # Create output queue
        output_queue = queue.Queue()
        
        # Start execution thread
        thread = threading.Thread(
            target=self.execute_module,
            args=(task_id, module_name, args, output_queue),
            daemon=True
        )
        
        self.running_tasks[task_id] = {
            'module': module_name,
            'thread': thread,
            'queue': output_queue,
            'status': 'running'
        }
        
        thread.start()
        return task_id
    
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get status of all tasks for dashboard."""
        tasks = []
        for task_id, task in self.running_tasks.items():
            status = self.get_task_status(task_id)
            if status:
                tasks.append(status)
        
        # Sort by status (running first, then complete, then error)
        status_order = {'running': 0, 'complete': 1, 'error': 2}
        tasks.sort(key=lambda x: status_order.get(x['status'], 3))
        return tasks
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get status and output of a running task."""
        if task_id not in self.running_tasks:
            return None
        
        task = self.running_tasks[task_id]
        
        # Collect all messages from queue
        messages = []
        while not task['queue'].empty():
            try:
                msg = task['queue'].get_nowait()
                messages.append(msg)
                
                # Update task status based on message type
                if msg['type'] == 'complete':
                    task['status'] = 'complete'
                    task['result'] = msg
                elif msg['type'] == 'error':
                    task['status'] = 'error'
                    task['result'] = msg
                    
            except queue.Empty:
                break
        
        # If thread is dead but status is still 'running', mark as complete
        if not task['thread'].is_alive() and task['status'] == 'running':
            # Check if we have a stored result
            if 'result' not in task:
                # Thread finished but no result message - assume success
                task['status'] = 'complete'
                task['result'] = {
                    'type': 'complete',
                    'stdout': '',
                    'stderr': '',
                    'success': True
                }
        
        return {
            'task_id': task_id,
            'module': task['module'],
            'status': task['status'],
            'messages': messages,
            'is_alive': task['thread'].is_alive(),
            'result': task.get('result')  # Include stored result
        }


# Global executor instance
executor = ModuleExecutor()
