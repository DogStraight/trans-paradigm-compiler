from rich.console import Console
from rich.layout import Layout
from rich.table import Table
from rich import print
richConsole = Console
rich_print = print
richTable = Table

if __name__ == "__main__":
    layout = Layout()
    layout.split_column(
        Layout(name="upper"),
        Layout(name="lower")
    )
    rich_print(layout.tree)
