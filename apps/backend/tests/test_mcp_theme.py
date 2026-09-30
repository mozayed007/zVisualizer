"""Contract tests for the generated widget theme assets (MCP render side).

Mirrors the surfaces guarded by the frontend bun test
(`apps/frontend/src/lib/__tests__/designTokens.test.ts`).
"""

from __future__ import annotations

from app.mcp.render.theme import widget_theme, widget_theme_css

REQUIRED_TOKEN_SURFACES = (
    "--color-background-primary",
    "--color-background-secondary",
    "--color-background-tertiary",
    "--color-text-primary",
    "--color-text-secondary",
    "--color-text-tertiary",
    "--color-border-secondary",
    "--color-border-tertiary",
    "--font-sans",
    "--font-mono",
    "--border-radius-md",
    "--p",
    "--s",
    "--t",
    "--bg2",
    "--b",
)

RAMP_NAMES = ("purple", "teal", "amber", "coral", "blue", "green", "pink", "gray", "red")


def test_theme_css_contains_token_and_ramp_surfaces() -> None:
    css = widget_theme_css()
    for token in REQUIRED_TOKEN_SURFACES:
        assert token in css, f"theme CSS lost required token: {token}"
    for ramp in RAMP_NAMES:
        assert f".c-{ramp} .box" in css, f"theme CSS lost class-based ramp rule: c-{ramp}"
        assert f".c-{ramp}>rect" in css, f"theme CSS lost direct-child ramp rule: c-{ramp}"
    for utility in (".box", "text.t{", "text.th{", "text.ts{", ".node{cursor:pointer}", ".leader{"):
        assert utility in css, f"theme CSS lost utility surface: {utility}"


def test_theme_token_values_match_design_tokens() -> None:
    theme = widget_theme()
    light = theme.tokens("light")
    dark = theme.tokens("dark")
    assert light["--color-text-primary"] == "#1a1918"
    assert light["--color-background-secondary"] == "#f4f2eb"
    assert dark["--color-text-primary"] == "#e8e6df"
    assert dark["--color-background-secondary"] == "#1a1a1f"


def test_resolve_follows_alias_chain() -> None:
    theme = widget_theme()
    assert theme.resolve("var(--p)", "light") == "#1a1918"
    assert theme.resolve("var(--p)", "dark") == "#e8e6df"
    assert theme.resolve("var(--b)", "light") == "rgba(0, 0, 0, 0.09)"
    assert theme.resolve("var(--b)", "dark") == "rgba(255, 255, 255, 0.08)"
    assert theme.resolve("#ff0000", "light") == "#ff0000"


def test_resolve_leaves_unknown_tokens_untouched() -> None:
    theme = widget_theme()
    resolved = theme.resolve("var(--not-a-token)", "light")
    assert resolved == "var(--not-a-token)"
    assert theme.has_unresolved_var(resolved or "") is True


def test_ramp_values_match_ramp_contract() -> None:
    theme = widget_theme()
    light = theme.ramp("purple", "light")
    assert (light.fill, light.stroke, light.title, light.subtitle) == (
        "#EEEDFE",
        "#534AB7",
        "#3C3489",
        "#534AB7",
    )
    dark = theme.ramp("purple", "dark")
    assert (dark.fill, dark.stroke, dark.title, dark.subtitle) == (
        "#3C3489",
        "#AFA9EC",
        "#CECBF6",
        "#AFA9EC",
    )
    direct_dark = theme.ramp("purple", "dark", variant="direct")
    assert direct_dark.stroke == "#534AB7"


def test_ramp_names_cover_supported_classes() -> None:
    assert widget_theme().ramp_names() == sorted(RAMP_NAMES)
