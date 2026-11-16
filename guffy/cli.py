"""
Guffy CLI entrypoint
"""

import sys
from rich.console import Console

console = Console()


def main():
    console.print("[bold green]Guffy AI Job Agent[/bold green] v0.1.0")
    console.print("Run [cyan]Guffy --help[/cyan] for available commands.")


if __name__ == "__main__":
    main()
