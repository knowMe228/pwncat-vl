#!/usr/bin/env python3
"""
Command to run a script either locally or on a remote target with real-time output streaming.
This command accepts a URL or local path to a script, downloads/copies it to the session directory,
determines the interpreter from the shebang, creates an output file, and runs the script
while streaming output in real-time.
"""

import os
import shlex
import shutil
import tempfile
import threading
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional

import pwncat
from pwncat.util import console
from pwncat.commands import Complete, Parameter, CommandDefinition


def is_url(s: str) -> bool:
    """Check if string is a URL (starts with http://, https://, or ftp://)"""
    try:
        result = urlparse(s)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def download_url(url: str) -> tuple[str, bytes]:
    """Download URL to memory, return filename and bytes"""
    import urllib.request
    
    response = urllib.request.urlopen(url)
    data = response.read()
    
    # Extract filename from URL
    filename = os.path.basename(url)
    if not filename or '.' not in filename:
        filename = 'script.sh'  # default
    
    return filename, data


def normalize_local_path(p: str) -> Path:
    """Expand ~, environment vars and return resolved path"""
    expanded = os.path.expanduser(os.path.expandvars(p))
    path = Path(expanded).resolve()
    
    if not path.exists():
        raise FileNotFoundError(f"File does not exist: {path}")
    
    return path


def make_session_dirs(session_dir: Path) -> Path:
    """Create session_dir/scripts/ and return script directory"""
    scripts_dir = session_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    return scripts_dir


def make_unique_names(scripts_dir: Path, src_name: str) -> tuple[Path, Path]:
    """Create unique script and output file paths with timestamp prefix"""
    from datetime import datetime
    
    timestamp = datetime.now().strftime("%Y_%m_%d-%H_%M_%S")
    safe_name = "".join(c for c in src_name if c.isalnum() or c in (' ', '.', '_', '-')).rstrip()
    
    script_path = scripts_dir / f"{timestamp}-{safe_name}"
    output_path = scripts_dir / f"{timestamp}-output.txt"
    
    return script_path, output_path


def save_bytes_to(path: Path, data: bytes) -> None:
    """Write binary data to path"""
    with open(path, 'wb') as f:
        f.write(data)


def detect_shebang(script_path: Path) -> str:
    """Read first line, return interpreter after #! or raise exception"""
    with open(script_path, 'rb') as f:
        first = f.readline()
    
    if not first.startswith(b'#!'):
        raise ValueError("No shebang detected in script. Please add a shebang line (e.g., #!/bin/bash) or specify interpreter explicitly.")
    
    interpreter = first[2:].decode('utf-8', errors='replace').strip()
    if not interpreter:
        raise ValueError("Invalid shebang format")
        
    return interpreter


def which_terminal() -> Optional[str]:
    """Find a terminal emulator in PATH"""
    terminals = ['alacritty', 'kitty']
    
    for terminal in terminals:
        if shutil.which(terminal):
            return terminal
    return None


def open_tail_terminal(output_path: Path, terminal: Optional[str] = None) -> bool:
    """Open a terminal running tail -f on the output path"""
    if not terminal:
        terminal = which_terminal()
    
    if not terminal:
        return False
    
    # Ensure the output file exists before attempting to tail it
    output_path.touch(exist_ok=True)
    
    if terminal in ['gnome-terminal', 'xfce4-terminal', 'konsole']:
        cmd = [terminal, '-e', 'bash', '-c', f'tail -n+0 -f "{output_path}"']
    elif terminal in ['xterm', 'rxvt', 'urxvt']:
        cmd = [terminal, '-e', 'bash', '-c', f'tail -n+0 -f "{output_path}"']
    else:
        cmd = [terminal, '-e', 'bash', '-c', f'tail -n+0 -f "{output_path}"']
    
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except Exception:
        return False


def local_tail_printer(output_path: Path) -> threading.Thread:
    """Start a thread that prints updates to the output file"""
    def tail_func():
        import time
        with open(output_path, 'r') as f:
            # Seek to end to only show new content
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    print(line, end='', flush=True)
                else:
                    time.sleep(0.1)
    
    thread = threading.Thread(target=tail_func, daemon=True)
    thread.start()
    return thread


def run_local(interpreter_cmd: str, script_path: Path, output_path: Path) -> int:
    """Run script locally with interpreter, stream to output file"""
    import shlex
    
    try:
        # Split the interpreter command properly
        parts = shlex.split(interpreter_cmd)
        
        with open(output_path, 'ab') as output_file:
            proc = subprocess.Popen(
                parts,
                stdin=subprocess.PIPE,
                stdout=output_file,
                stderr=subprocess.STDOUT
            )
            
            # Read and send script content to stdin
            with open(script_path, 'rb') as script_file:
                while True:
                    chunk = script_file.read(8192)
                    if not chunk:
                        break
                    proc.stdin.write(chunk)
            
            proc.stdin.close()
            proc.wait()
            return proc.returncode
    
    except Exception as e:
        console.log(f"[red]error[/red]: failed to run script locally: {str(e)}")
        return -1


class Command(CommandDefinition):
    """
    Run a script either locally or through the current session. This command accepts
    a URL or local path to a script, downloads/copies it to the session directory,
    determines the interpreter from the shebang, creates an output file, and runs the script
    while streaming output in real-time.
    
    Examples:
      script /path/to/local/script.sh
      script https://example.com/script.sh
      script --no-tail /path/to/script.sh
      script --force-interpreter /bin/bash /path/to/script.sh
    """

    PROG = "script"
    LOCAL = False  # This command can work with sessions

    ARGS = {
        "--no-tail": Parameter(
            Complete.NONE, action="store_true",
            help="Don't open a terminal to monitor output in real-time"
        ),
        "--force-interpreter": Parameter(
            Complete.LOCAL_FILE,
            help="Force a specific interpreter instead of detecting from shebang",
            metavar="INTERPRETER"
        ),
        "--mode": Parameter(
            Complete.CHOICES,
            choices=["local", "session"],
            help="Execution mode: local or through session",
            default="session"
        ),
        "source": Parameter(
            Complete.LOCAL_FILE,
            help="URL or local path to the script to execute",
            metavar="SOURCE"
        )
    }

    def run(self, manager: "pwncat.manager.Manager", args):
        from datetime import datetime
        
        # Launch the actual execution in a background thread to avoid blocking the main terminal
        thread = threading.Thread(
            target=self._execute_script,
            args=(manager, args)
        )
        thread.daemon = True
        thread.start()
        
        console.log("[green]script execution started in background. Main terminal is now available for other commands.")
        console.log("[green]You can monitor the output in the opened terminal or check the output file when complete.")

    def _execute_script(self, manager: "pwncat.manager.Manager", args):
        """Internal method that executes the script in the background thread."""
        from datetime import datetime
        
        # Validate input
        if not args.source:
            console.log("[red]error[/red]: no source script provided")
            return

        # Create session directory if we have a session
        if manager.target is not None:
            session_dir = Path(manager.target.db.root.path) if hasattr(manager.target.db.root, 'path') else Path(tempfile.gettempdir()) / "pwncat_session"
        else:
            session_dir = Path(tempfile.gettempdir()) / "pwncat_local"
        
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Prepare directories
        try:
            scripts_dir = make_session_dirs(session_dir)
        except Exception as e:
            console.log(f"[red]error[/red]: failed to create session directories: {str(e)}")
            return

        # Get script content based on source type
        if is_url(args.source):
            try:
                console.log(f"[blue]downloading[/blue]: {args.source}")
                filename, data = download_url(args.source)
                script_path, output_path = make_unique_names(scripts_dir, filename)
                save_bytes_to(script_path, data)
            except Exception as e:
                console.log(f"[red]error[/red]: failed to download {args.source}: {str(e)}")
                return
        else:
            try:
                local_path = normalize_local_path(args.source)
                script_path, output_path = make_unique_names(scripts_dir, local_path.name)
                save_bytes_to(script_path, local_path.read_bytes())
            except Exception as e:
                console.log(f"[red]error[/red]: failed to access {args.source}: {str(e)}")
                return

        # Determine interpreter
        if args.force_interpreter:
            interpreter = args.force_interpreter
        else:
            try:
                interpreter = detect_shebang(script_path)
            except ValueError as e:
                console.log(f"[red]error[/red]: {str(e)}")
                console.log("[yellow]hint[/yellow]: use --force-interpreter to specify an interpreter")
                return

        console.log(f"[green]using interpreter[/green]: {interpreter}")
        console.log(f"[blue]output file[/blue]: {output_path}")

        # Set up real-time output monitoring if not disabled
        if not args.no_tail:
            terminal = which_terminal()
            if terminal and open_tail_terminal(output_path, terminal):
                console.log(f"[green]opened monitoring terminal with[/green]: {terminal}")
            else:
                console.log("[yellow]warning[/yellow]: no terminal emulator found, starting local tail thread")
                local_tail_printer(output_path)

        # Execute based on mode
        if args.mode == "local":
            exit_code = run_local(interpreter, script_path, output_path)
        elif args.mode == "session" and manager.target is not None:
            exit_code = self.run_via_session(manager.target, interpreter, script_path, output_path)
        elif args.mode == "session" and manager.target is None:
            console.log("[red]error[/red]: session mode selected but no active session")
            return
        else:
            console.log(f"[red]error[/red]: unknown mode: {args.mode}")
            return

        console.log(f"[green]execution completed[/green]: exit code {exit_code}")
        console.log(f"[blue]output saved to[/blue]: {output_path}")

    def run_via_session(self, session, interpreter_cmd: str, script_path: Path, output_path: Path) -> int:
        """Run the script through the active session"""
        try:
            # Read the script content
            with open(script_path, 'rb') as f:
                script_content = f.read()

            # Create temporary file on the target
            remote_script_path = f"/tmp/{script_path.name}"
            console.log(f"[blue]uploading script to[/blue]: {remote_script_path}")
            
            # Write script to remote target
            with session.platform.open(remote_script_path, "wb") as remote_file:
                remote_file.write(script_content)
            
            # Make the script executable
            session.platform.run(f"chmod +x {remote_script_path}", capture_output=True)
            
            # Prepare the interpreter command with the remote script
            full_cmd = f"{interpreter_cmd} {remote_script_path}"
            
            console.log(f"[green]executing[/green]: {full_cmd}")
            
            # Execute the script and stream output to file
            with open(output_path, 'wb') as output_file:
                # We'll use Popen to stream output in real-time
                proc = session.platform.Popen(
                    shlex.split(full_cmd),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT
                )
                
                for line in proc.stdout:
                    output_file.write(line)
                    output_file.flush()
                
                proc.wait()
                exit_code = proc.returncode
            
            # Clean up the temporary script file on target
            try:
                session.platform.run(f"rm -f {remote_script_path}", capture_output=True)
            except:
                pass  # Ignore cleanup errors
            
            return exit_code
            
        except Exception as e:
            console.log(f"[red]error[/red]: failed to execute script via session: {str(e)}")
            return -1