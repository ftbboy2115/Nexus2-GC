"""
Documentation Routes

Serves README and other documentation content to the frontend.
"""

from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/documentation", tags=["documentation"])


@router.get("/readme", response_class=PlainTextResponse)
async def get_readme():
    """
    Get the README.md content for display in the frontend.
    
    Returns raw markdown text that the frontend can render.
    """
    import os
    
    # Find nexus2 package location
    import nexus2
    nexus2_root = Path(nexus2.__file__).parent
    readme_path = nexus2_root / "README.md"
    
    if readme_path.exists():
        return readme_path.read_text(encoding="utf-8")
    
    # Fallback to working directory
    cwd_readme = Path.cwd() / "nexus2" / "README.md"
    if cwd_readme.exists():
        return cwd_readme.read_text(encoding="utf-8")
    
    return f"# README not found\n\nTried:\n- {readme_path}\n- {cwd_readme}"
