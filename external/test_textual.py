from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Static


class ButtonsApp(App[str]):
    CSS_PATH = "button.css"

    def compose(self) -> ComposeResult:
        page_content = Horizontal(
            VerticalScroll(
                Static("Standard Buttons", classes="header"),
                Button("Default"),
                Button("Primary!", variant="primary"),
            ),
        )
        yield page_content

    def on_button_pressed(self, event: Button.Pressed) -> None:
        # self.exit(str(event.button))
        self.exit(f"{str(event.button)}")


if __name__ == "__main__":
    app = ButtonsApp()
    print(app.run())
