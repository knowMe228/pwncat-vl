#!/usr/bin/env python3

from pwncat.db import Fact
from pwncat.modules.enumerate import Schedule, EnumerateModule
from pwncat.platform.linux import Linux


class HelloWorld(Fact):
    """
    A simple hello world fact
    """

    def __init__(self, source):
        super().__init__(source=source, types=["hello.world"])

    def title(self, session):
        return "[green]Hello World[/green] - A simple test fact"

    def description(self, session):
        return "This is a simple hello world output from a pwncat module."


class Module(EnumerateModule):
    """
    A simple hello world module that outputs hello world
    """

    PROVIDES = ["hello.world"]
    PLATFORM = [Linux]
    SCHEDULE = Schedule.ONCE

    def enumerate(self, session):
        """
        Output hello world
        """
        print("Hello World from pwncat module!")
        yield HelloWorld(self.name)