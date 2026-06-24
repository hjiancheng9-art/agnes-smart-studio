"""Organic animation and transition effects for terminal output.

Provides subtle visual feedback for mode switches, generation completion,
and thinking states. All effects use time.sleep() — only use in
non-streaming contexts (never inside StreamingRenderer flow).

Note: fade_in and animated_banner produce multi-line output; they are
NOT compatible with the StreamingRenderer transient Live contract.
Only call these between renderer.stop() and renderer.start() boundaries,
or in standalone contexts outside streaming.
"""

import time

from ui.theme import COLORS, ICONS, console

__all__ = [
    "fade_in",
    "animated_banner",
    "success_pulse",
    "thinking_dots",
]


def fade_in(content: str, duration: float = 0.3, steps: int = 4):
    """Dim-to-normal fade-in for Panel or text content.

    Prints dim version first, waits, then prints full version.
    The dim version is overwritten by the normal version in terminal scroll.
    Only use outside StreamingRenderer flow.
    """
    console.print(content, style="dim")
    time.sleep(duration)
    console.print(content)


def animated_banner(session):
    """Print prominent badge banner with dim-to-bright transition on mode switch.

    First shows dim version, then overwrites with bright version.
    Only use outside StreamingRenderer flow.
    """
    from ui.badges import session_badges

    badges = session_badges(session)
    if not badges:
        return
    sep = f" [{COLORS['muted']}]{ICONS['info']}[/] "
    line = sep.join(b.render(dim=False) for b in badges)
    # Dim preview → bright final
    console.print(f"  {line}", style="dim")
    time.sleep(0.12)
    console.print(f"  {line}")


def success_pulse(message: str, pulses: int = 2):
    """Success message with brief bold-dim pulse effect.

    Alternates between bold and dim for `pulses` cycles, settling on normal.
    Only use outside StreamingRenderer flow.
    """
    for _ in range(pulses):
        console.print(f"[{COLORS['success']} bold]{message}[/]")
        time.sleep(0.06)
        console.print(f"[{COLORS['success']} dim]{message}[/]")
        time.sleep(0.06)
    console.print(f"[{COLORS['success']}]{message}[/]")  # Steady state


def thinking_dots(duration: float = 30.0):
    """Flowing dot animation for thinking/processing state.

    Prints pulsating organic dots (∘ ◦ ∙ ● ∙ ◦) in a single line,
    overwriting each frame. Returns after `duration` seconds.
    Only use outside StreamingRenderer flow.
    """
    frames = ["∘", "◦", "∙", "●", "∙", "◦"]
    interval = 0.2
    steps = int(duration / interval)
    for i in range(steps):
        frame = frames[i % len(frames)]
        console.print(f"\r  [{COLORS['transition']}]{frame} Thinking...[/]", end="")
        time.sleep(interval)
    console.print()  # Final newline
