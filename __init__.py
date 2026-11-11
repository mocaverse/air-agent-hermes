"""AIR Agent KYA: AIR Know-Your-Agent for Hermes (port of mocaverse/air-kya agent/)."""

from __future__ import annotations

from pathlib import Path

TOOLSET = "air_agent_kya"


def register(ctx):
    from . import schemas, tools

    tools.bind_ctx(ctx)

    ctx.register_tool(name="air_whoami", toolset=TOOLSET, schema=schemas.AIR_WHOAMI, handler=tools.air_whoami)
    ctx.register_tool(name="kya_visit", toolset=TOOLSET, schema=schemas.KYA_VISIT, handler=tools.kya_visit)
    ctx.register_hook("pre_tool_call", tools.pre_tool_call)

    ctx.register_cli_command(name="air", help="AIR Agent KYA: delegate AIR identity and visit KYA sites",
                             setup_fn=tools.cli_setup, handler_fn=tools.cli_handler)
    ctx.register_command("air", handler=tools.slash_air, description="AIR Agent KYA delegation status")

    skills_dir = Path(__file__).parent / "skills"
    for child in sorted(skills_dir.iterdir()) if skills_dir.exists() else []:
        if child.is_dir() and (child / "SKILL.md").exists():
            ctx.register_skill(child.name, child / "SKILL.md")
