from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import click
from rich.console import Console
from textual import log, events
from textual.app import ComposeResult, App, AutopilotCallbackType
from textual.containers import VerticalScroll, Vertical, Horizontal
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import (
    Pretty,
    Tree,
    Label,
    Static,
    Button,
)
from textual.widgets.tree import TreeNode

from textual_click.form import CommandForm
from textual_click.introspect import (
    introspect_click_app,
    CommandSchema,
)
from textual_click.run_command import UserCommandData
from textual_click.widgets.command_tree import CommandTree


class CommandBuilder(Screen):
    def __init__(
        self,
        cli: click.BaseCommand,
        click_app_name: str,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ):
        super().__init__(name, id, classes)
        self.command_data = None
        self.cli = cli
        self.command_schemas = introspect_click_app(cli)
        self.click_app_name = click_app_name

    def compose(self) -> ComposeResult:
        tree = CommandTree("", self.command_schemas)

        sidebar = Vertical(
            Label("Command Tree", id="home-commands-label"),
            tree,
            id="home-sidebar",
        )
        if isinstance(self.cli, click.Group):
            # If the root of the click app is a Group instance, then
            #  we display the command tree to users.
            tree.focus()
        else:
            # If the click app is structured using a single command,
            #  there's no need for us to display the command tree.
            sidebar.display = False
        yield sidebar

        scrollable_body = VerticalScroll(
            Pretty(self.command_schemas),
            id="home-body-scroll",
        )
        body = Vertical(
            Static("", id="home-command-description"),
            scrollable_body,
            Horizontal(
                Static("", id="home-exec-preview-static"),
                Vertical(
                    Button.success("Execute"),
                    id="home-exec-preview-buttons",
                ),
                id="home-exec-preview",
            ),
            id="home-body",
        )
        scrollable_body.can_focus = True
        yield body

    def on_mount(self, event: events.Mount) -> None:
        self._refresh_command_form()

    def _refresh_command_form(self, node: TreeNode[CommandSchema] | None = None):
        if node is None:
            try:
                command_tree = self.query_one(CommandTree)
                node = command_tree.cursor_node
            except NoMatches:
                return
        self.selected_command_schema = node.data
        self._update_command_description(node)
        self._update_execution_string_preview(self.selected_command_schema, self.command_data)
        self._update_form_body(node)

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted[CommandSchema]) -> None:
        """When we highlight a node in the CommandTree, the main body of the home page updates
        to display a form specific to the highlighted command."""
        # TODO: Add an ID check
        self._refresh_command_form(event.node)

    def on_command_form_changed(self, event: CommandForm.Changed) -> None:
        self.command_data = event.command_data
        self._update_execution_string_preview(self.selected_command_schema, self.command_data)
        log(event.command_data.to_cli_string())

    def _update_command_description(self, node: TreeNode[CommandSchema]) -> None:
        """Update the description of the command at the bottom of the sidebar
        based on the currently selected node in the command tree."""
        description_box = self.query_one("#home-command-description", Static)
        description_text = node.data.docstring or ""
        description_text = f"[b]{node.label}[/]\n{description_text}"
        description_box.update(description_text)

    def _update_execution_string_preview(self, command_schema: CommandSchema, command_data: UserCommandData) -> None:
        """Update the preview box showing the command string to be executed"""
        if self.command_data is not None:
            self.query_one("#home-exec-preview-static", Static).update(
                command_data.to_cli_string()
            )

    def _update_form_body(self, node: TreeNode[CommandSchema]) -> None:
        # self.query_one(Pretty).update(node.data)
        parent = self.query_one("#home-body-scroll", VerticalScroll)
        for child in parent.children:
            child.remove()

        # Process the metadata for this command and mount corresponding widgets
        command_schema = node.data
        parent.mount(
            CommandForm(
                command_schema=command_schema, command_schemas=self.command_schemas
            )
        )


class TextualClick(App):
    CSS_PATH = Path(__file__).parent / "textual_click.scss"

    def __init__(self, cli: click.Group, app_name: str = None) -> None:
        super().__init__()
        self.cli = cli
        self.app_name = app_name
        # TODO: Don't hardcode ls
        self.post_run_command: list[str] = ["ls"]

    def on_mount(self):
        self.push_screen(CommandBuilder(self.cli, self.app_name))

    def run(
        self,
        *,
        headless: bool = False,
        size: tuple[int, int] | None = None,
        auto_pilot: AutopilotCallbackType | None = None,
    ) -> None:
        try:
            super().run(headless=headless, size=size, auto_pilot=auto_pilot)
        finally:
            # TODO: Make this happen only when you Execute/Save+Execute
            if self.post_run_command:
                console = Console()
                console.print(f"Running [b cyan]{shlex.join(self.post_run_command)}[/]")
                subprocess.run(self.post_run_command)


def tui():
    def decorator(app: click.Group | click.Command):
        def wrapped_tui(*args, **kwargs):
            TextualClick(app).run()
            # Call the original command function
            # app.callback(*args, **kwargs)

        if isinstance(app, click.Group):
            app.command(name="tui")(wrapped_tui)
        else:
            new_group = click.Group()
            new_group = click.Group()
            new_group.add_command(app)
            new_group.command(name="tui")(wrapped_tui)
            return new_group

        return app

    return decorator
