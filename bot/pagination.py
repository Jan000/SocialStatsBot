"""
Reusable pagination View for Discord embeds.

Usage:
    pages = [embed1, embed2, embed3]
    view = PaginationView(pages, author_id=interaction.user.id)
    await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)
"""

from __future__ import annotations

import discord


class PaginationView(discord.ui.View):
    """A View with previous/next buttons for paginating embed pages."""

    def __init__(
        self,
        pages: list[discord.Embed],
        *,
        author_id: int,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.pages = pages
        self.author_id = author_id
        self.current = 0
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_button.disabled = self.current <= 0
        self.next_button.disabled = self.current >= len(self.pages) - 1
        self.page_label.label = f"{self.current + 1}/{len(self.pages)}"

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Nicht deine Nachricht.", ephemeral=True)
            return
        self.current = max(0, self.current - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_label(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pass  # non-interactive label

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Nicht deine Nachricht.", ephemeral=True)
            return
        self.current = min(len(self.pages) - 1, self.current + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


def paginate_lines(lines: list[str], per_page: int = 15) -> list[list[str]]:
    """Split a list of lines into chunks for pagination."""
    return [lines[i:i + per_page] for i in range(0, len(lines), per_page)]
