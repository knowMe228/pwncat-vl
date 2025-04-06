#!/usr/bin/env python3
from rich import box
from rich.table import Table

from pwncat.util import console
from pwncat.commands import Complete, Parameter, CommandDefinition


class Command(CommandDefinition):
    """
    Remember arbitrary key-value pairs during the session.
    Useful to store tokens, passwords, paths, etc.
    """

    PROG = "remember"
    ARGS = {
        "action": Parameter(
            Complete.CHOICES,
            choices=["set", "get", "list", "clear", "export"],
            help="Action: set/get/list/clear/export",
        ),
        "key": Parameter(Complete.NONE, nargs="?", help="Key to use or fetch"),
        "value": Parameter(Complete.NONE, nargs="?", help="Value to store"),
    }

    def run(self, manager: "pwncat.manager.Manager", args):
        if not hasattr(manager, "remember"):
            manager.remember = {}

        memory = manager.remember

        def do_set():
            if not args.key or not args.value:
                self.parser.error("Usage: remember set <key> <value>")
            memory[args.key] = args.value
            console.log(f"Stored [cyan]{args.key}[/cyan]")

        def do_get():
            if not args.key:
                self.parser.error("Usage: remember get <key>")
            value = memory.get(args.key)
            if value is not None:
                table = Table(box=box.MINIMAL_DOUBLE_HEAD)
                table.add_column("Key", style="cyan", no_wrap=True)
                table.add_column("Value", style="green")
                table.add_row(args.key, value)
                console.print(table)
            else:
                console.log(f"[yellow]Key not found:[/yellow] {args.key}")

        def do_list():
            if not memory:
                console.log("[yellow]No remembered values.[/yellow]")
                return
            table = Table(title="Remembered Values", box=box.MINIMAL_DOUBLE_HEAD)
            table.add_column("Key", style="cyan", no_wrap=True)
            table.add_column("Value", style="green")
            for k, v in memory.items():
                table.add_row(k, v)
            console.print(table)

        def do_clear():
            memory.clear()
            console.log("All remembered values cleared.")

        def do_export():
            import json

            console.print_json(data=memory)

        dispatch = {
            "set": do_set,
            "get": do_get,
            "list": do_list,
            "clear": do_clear,
            "export": do_export,
        }

        if args.action not in dispatch:
            self.parser.error("Unknown action. Use: set, get, list, clear, export")

        dispatch[args.action]()
