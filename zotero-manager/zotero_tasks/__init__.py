"""
zotero_tasks - collection of Zotero library maintenance tasks.

Each module exposes two functions:
    add_arguments(parser)  - registers CLI arguments for the subcommand
    run(args)              - executes the task
"""
from . import clear_extra, fix_titles

__all__ = ["clear_extra", "fix_titles"]
