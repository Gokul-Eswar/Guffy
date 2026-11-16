"""
HuntFlow CLI entrypoint
"""

import sys
from rich.console import Console

console = Console()


def main():
    console.print("[bold green]HuntFlow AI Job Agent[/bold green] v0.1.0")
    console.print("Run [cyan]huntflow --help[/cyan] for available commands.")


if __name__ == "__main__":
    main()
