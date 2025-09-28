#!/usr/bin/env python3

import os
import subprocess
from typing import Generator

import rich.markup

import pwncat
from pwncat.db import Fact
from pwncat.platform.linux import Linux
from pwncat.modules.enumerate import Schedule, EnumerateModule


class SuidTreeFile(Fact):
    """
    A file with the SUID bit set, displayed in a tree format
    """

    def __init__(self, source, path, uid):
        super().__init__(source=source, types=["file.suid.tree"])
        
        self.path = path
        self.uid = uid

    def title(self, session):
        color = "red" if self.uid == 0 else "green"
        return f"[cyan]{rich.markup.escape(self.path)}[/cyan] owned by [{color}]{rich.markup.escape(session.find_user(uid=self.uid).name)}[/{color}]"


class Module(EnumerateModule):
    """
    Find all files with the SUID bit set and display them in a tree structure
    """

    PROVIDES = ["file.suid.tree"]
    PLATFORM = [Linux]
    SCHEDULE = Schedule.ONCE

    def enumerate(self, session: "pwncat.manager.Session"):
        """
        Find all files with SUID bit set and yield them as facts in a tree structure
        """
        # This forces the session to enumerate users FIRST, so we don't run
        # into trying to enumerate _whilst_ enumerating SUID binaries...
        session.find_user(uid=0)

        # Collect SUID files by directory for tree display
        suid_files_by_dir = {}
        
        # Spawn a find command to locate the setuid binaries
        proc = session.platform.Popen(
            ["find", "/", "-perm", "-4000", "-printf", "%U %p\\n"],
            stderr=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            text=True,
        )

        try:
            with proc.stdout as stream:
                for line in stream:
                    line = line.strip()
                    if not line:
                        continue
                    # Parse out owner ID and path
                    parts = line.split(" ", 1)
                    if len(parts) != 2:
                        continue
                    uid, path = int(parts[0]), parts[1]
                    
                    # Group by directory for tree structure
                    directory = os.path.dirname(path)
                    filename = os.path.basename(path)
                    
                    if directory not in suid_files_by_dir:
                        suid_files_by_dir[directory] = []
                    suid_files_by_dir[directory].append((filename, uid, path))

            # Sort directories for consistent output
            sorted_dirs = sorted(suid_files_by_dir.keys())
            
            # Print a tree-like representation of SUID files
            # Using the session's print function for proper Rich markup processing
            session.print("[blue]SUID Files Tree:[/blue]")
            session.print()  # blank line
            
            for directory in sorted_dirs:
                session.print(f"[green]{directory}[/green]")
                
                # Sort files within each directory
                files_in_dir = sorted(suid_files_by_dir[directory], key=lambda x: x[0])
                for filename, uid, full_path in files_in_dir:
                    user = session.find_user(uid=uid).name
                    user_color = "red" if uid == 0 else "yellow"
                    session.print(f"├── [yellow]{filename}[/yellow] (owned by [{user_color}]{user}[/{user_color}])")
                session.print()  # blank line after each directory
            
            # Yield each SUID file as a fact
            for directory in sorted_dirs:
                files_in_dir = sorted(suid_files_by_dir[directory], key=lambda x: x[0])
                for filename, uid, full_path in files_in_dir:
                    yield SuidTreeFile(self.name, full_path, uid)
                    
        except Exception as e:
            # Handle potential Rich import issues or other errors
            session.print(f"Warning: Could not enumerate SUID files: {e}")
            return
        finally:
            proc.wait()