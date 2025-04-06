#!/usr/bin/env python3
import os
import time

from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    DownloadColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

import pwncat
from pwncat import util
from pwncat.util import console
from pwncat.commands import Complete, Parameter, CommandDefinition


class Command(CommandDefinition):
    """
    Download a file from the remote host to the local host.
    If --recursive is specified and the source is a directory,
    recursively download its contents into the local destination,
    preserving the remote subdirectory structure.

    The top-level remote directory is not recreated inside the destination;
    only its contents (and subdirectories) are downloaded.
    """

    PROG = "download"
    ARGS = {
        "source": Parameter(Complete.REMOTE_FILE),
        "destination": Parameter(Complete.LOCAL_FILE, nargs="?"),
        "--recursive": Parameter(
            Complete.NONE, action="store_true", help="Recursively download directories"
        ),
    }

    def run(self, manager: "pwncat.manager.Manager", args):
        """
        Execute the download command.

        For a single file, download the remote file to the specified local destination.
        For directories (when --recursive is provided), recursively traverse the remote
        directory, compute total size and file count, then download all files using a
        single global progress bar. At the end, a summary is printed.

        :param manager: The pwncat manager object.
        :param args: Command line arguments.
        """
        # Global progress bar for all downloads.
        progress = Progress(
            TextColumn("[bold cyan]{task.fields[filename]}", justify="right"),
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "•",
            DownloadColumn(),
            "•",
            TransferSpeedColumn(),
            "•",
            TimeRemainingColumn(),
        )

        # Compute the total size and file count recursively.
        def compute_totals(remote_dir, visited=None):
            """
            Recursively compute the total size and file count of all files within a remote directory.

            :param remote_dir: A pwncat Path object representing a remote directory.
            :param visited: A set to track visited directories (to avoid infinite recursion).
            :return: A tuple (total_size, file_count).
            """
            if visited is None:
                visited = set()
            rstr = str(remote_dir)
            if rstr in visited:
                return 0, 0
            visited.add(rstr)

            # Process files in the current directory.
            files = [
                child
                for child in remote_dir.iterdir()
                if not child.is_dir()
                and os.path.basename(str(child)) not in {".", ".."}
            ]
            total_size = sum(child.stat().st_size for child in files if child.stat())
            file_count = len(files)

            # Process subdirectories.
            for child in remote_dir.iterdir():
                if child.is_dir() and os.path.basename(str(child)) not in {".", ".."}:
                    sub_size, sub_count = compute_totals(child, visited)
                    total_size += sub_size
                    file_count += sub_count

            return total_size, file_count

        # Download a single file and update the global progress.
        def download_file(remote_path, local_path, task_id, display_name):
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            start_time = time.time()
            with open(local_path, "wb") as lf, remote_path.open("rb") as rf:
                for buf in iter(lambda: rf.read(4096), b""):
                    lf.write(buf)
                    progress.update(task_id, advance=len(buf), filename=display_name)
            elapsed = time.time() - start_time
            console.log(
                f"downloaded [cyan]{util.human_readable_size(remote_path.stat().st_size)}[/cyan] in [green]{util.human_readable_delta(elapsed)}[/green] \u2192 {local_path}"
            )

        def traverse_and_download(
            remote_dir, local_base, base_remote, task_id, visited, file_list
        ):
            """
            Recursively traverse the remote directory and download all files,
            preserving the directory structure relative to base_remote.

            :param remote_dir: A pwncat Path object for the current remote directory.
            :param local_base: The local destination base directory.
            :param base_remote: The string representation of the base remote directory.
            :param task_id: The global progress task ID.
            :param visited: A set of visited remote directory paths to avoid infinite recursion.
            :param file_list: A list to collect the paths of downloaded files.
            """
            remote_str = str(remote_dir)
            if remote_str in visited:
                return
            visited.add(remote_str)

            for child in remote_dir.iterdir():
                child_name = os.path.basename(str(child))
                if child_name in [".", ".."]:
                    continue
                relative_path = os.path.relpath(str(child), base_remote)
                local_child = os.path.join(local_base, relative_path)
                if child.is_dir():
                    os.makedirs(local_child, exist_ok=True)
                    traverse_and_download(
                        child, local_base, base_remote, task_id, visited, file_list
                    )
                else:
                    download_file(child, local_child, task_id, relative_path)
                    file_list.append(local_child)

        try:
            remote = manager.target.platform.Path(args.source)

            if remote.is_dir():
                if not args.recursive:
                    self.parser.error(
                        "Source is a directory. Use --recursive to download it recursively."
                    )

                # Use the basename of the remote directory if no destination is provided.
                if not args.destination:
                    args.destination = os.path.basename(args.source)
                os.makedirs(args.destination, exist_ok=True)

                total_size, file_count = compute_totals(remote, set())
                console.log(
                    f"Total size to download: {total_size} bytes in {file_count} files."
                )

                downloaded_files = []
                with progress:
                    task_id = progress.add_task(
                        "download", filename="", total=total_size, start=True
                    )
                    traverse_and_download(
                        remote,
                        args.destination,
                        str(remote),
                        task_id,
                        set(),
                        downloaded_files,
                    )

                console.log(
                    f"Finished downloading {len(downloaded_files)} files ({util.human_readable_size(total_size)} total)."
                )
            else:
                # Handle single file download.
                if not args.destination:
                    args.destination = os.path.basename(args.source)
                elif os.path.isdir(args.destination):
                    args.destination = os.path.join(
                        args.destination, os.path.basename(args.source)
                    )

                total_size = remote.stat().st_size
                with progress:
                    task_id = progress.add_task(
                        "download", filename=str(remote), total=total_size, start=True
                    )
                    download_file(remote, args.destination, task_id, str(remote))

                console.log(f"Finished downloading file: {args.destination}")
        except (FileNotFoundError, PermissionError, IsADirectoryError) as exc:
            self.parser.error(str(exc))
