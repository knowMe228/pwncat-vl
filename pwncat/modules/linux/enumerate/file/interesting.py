#!/usr/bin/env python3

import subprocess
import os

from pwncat.db import Fact
from pwncat.platform.linux import Linux
from pwncat.modules.enumerate import Schedule, EnumerateModule


class InterestingFile(Fact):
    """An interesting file based on permissions or location"""
    
    def __init__(self, source, path, size, owner, group, permissions, description):
        super().__init__(source=source, types=["file.interesting"])
        
        self.path = path
        self.size = size
        self.owner = owner
        self.group = group
        self.permissions = permissions
        self.description = description

    def title(self, session):
        return f"[yellow]{self.path}[/yellow] ({self.description})"

    def description(self, session):
        return f"Path: {self.path}\\nSize: {self.size} bytes\\nOwner: {self.owner}:{self.group}\\nPermissions: {self.permissions}\\nNote: {self.description}"


class Module(EnumerateModule):
    """Find interesting files based on permissions and location"""
    
    PROVIDES = ["file.interesting"]
    PLATFORM = [Linux]
    SCHEDULE = Schedule.ONCE

    def enumerate(self, session):
        """Find world-writable files, files in /tmp, and files with interesting extensions"""
        
        # Find world-writable files outside /tmp (potential security risk)
        try:
            session.print("[blue]Searching for interesting files...[/blue]")
            
            # Find world-writable files outside /tmp
            result = session.platform.run(
                ["find", "/", "-type", "f", "-perm", "-002", "-not", "-path", "/tmp/*", 
                 "-not", "-path", "/var/tmp/*", "-not", "-path", "/dev/*", "-not", "-path", "/proc/*",
                 "-not", "-path", "/sys/*", "-not", "-path", "/run/*", "-not", "-path", "/mnt/*", 
                 "-not", "-path", "/media/*", "-not", "-path", "*/snap/*", "-print"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode in [0, 1]:  # 0 = success, 1 = found but some errors
                for path in result.stdout.strip().split('\\n'):
                    path = path.strip()
                    if path:
                        try:
                            # Get file stats
                            stat_result = session.platform.run(
                                ["stat", "-c", "%s %U %G %A", path],
                                capture_output=True,
                                text=True,
                                timeout=10
                            )
                            
                            if stat_result.returncode == 0:
                                parts = stat_result.stdout.strip().split(None, 3)
                                if len(parts) >= 4:
                                    size, owner, group, perms = parts[0], parts[1], parts[2], parts[3]
                                    desc = "World-writable file outside /tmp"
                                    yield InterestingFile(self.name, path, size, owner, group, perms, desc)
                        except:
                            # If we can't get stats, still report the file
                            yield InterestingFile(self.name, path, "unknown", "unknown", "unknown", "???", "World-writable file outside /tmp")
            
            # Find files with interesting extensions (config files, logs, etc.)
            interesting_extensions = [
                ".sql", ".db", ".conf", ".cfg", ".ini", ".log", ".bkp", 
                ".backup", ".old", ".yaml", ".yml", ".json", ".env", 
                ".pem", ".key", ".cert", ".crt"
            ]
            
            for ext in interesting_extensions:
                try:
                    result = session.platform.run(
                        ["find", "/home", "/tmp", "/var", "/opt", "-name", f"*{ext}", "-type", "f", "-print"],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    if result.returncode in [0, 1]:
                        for path in result.stdout.strip().split('\\n'):
                            path = path.strip()
                            if path:
                                try:
                                    stat_result = session.platform.run(
                                        ["stat", "-c", "%s %U %G %A", path],
                                        capture_output=True,
                                        text=True,
                                        timeout=10
                                    )
                                    
                                    if stat_result.returncode == 0:
                                        parts = stat_result.stdout.strip().split(None, 3)
                                        if len(parts) >= 4:
                                            size, owner, group, perms = parts[0], parts[1], parts[2], parts[3]
                                            desc = f"File with potentially interesting extension: {ext}"
                                            yield InterestingFile(self.name, path, size, owner, group, perms, desc)
                                except:
                                    yield InterestingFile(self.name, path, "unknown", "unknown", "unknown", "???", f"File with extension: {ext}")
                
                except subprocess.TimeoutExpired:
                    session.print(f"[yellow]Search for files with extension {ext} timed out[/yellow]")
                    continue
                except Exception as e:
                    session.print(f"[yellow]Error searching for {ext} files: {e}[/yellow]")
                    continue
                    
        except Exception as e:
            session.print(f"[red]Error finding interesting files: {e}[/red]")
            return