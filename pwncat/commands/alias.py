#!/usr/bin/env python3

from pwncat.util import console
from pwncat.commands import Complete, Parameter, CommandDefinition


class Command(CommandDefinition):
    """
    Alias an existing command with a new name. Specifying no alias or command
    will list all aliases. Specifying an alias with no command will remove the
    alias if it exists.
    """

    PROG = "alias"
    ARGS = {
        "alias": Parameter(Complete.NONE, help="name for the new alias", nargs="?"),
        "command": Parameter(
            Complete.NONE,
            metavar="COMMAND",
            help="the command the new alias will use",
            nargs="*",
        ),
    }
    LOCAL = True

    def run(self, manager, args):
        if args.alias is None:
            for name, command in manager.parser.aliases.items():
                console.print(f" [cyan]{name}[/cyan] \u2192 [yellow]{command}[/yellow]")
        elif args.command:
            full_command = " ".join(args.command)
            manager.parser.aliases[args.alias] = full_command
        else:
            if args.alias in manager.parser.aliases:
                del manager.parser.aliases[args.alias]
                console.log(f"Alias '{args.alias}' removed")
            else:
                console.log(f"[yellow]Alias '{args.alias}' not found[/yellow]")
