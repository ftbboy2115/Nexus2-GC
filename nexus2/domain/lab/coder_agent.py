"""
Coder Agent - Auto-generate strategy code from hypothesis.

Takes a hypothesis from the Researcher Agent and generates:
- config.yaml: Strategy configuration
- scanner.py: Signal discovery
- engine.py: Entry detection
- monitor.py: Position management
- test_strategy.py: Unit tests
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


# =============================================================================
# MODELS
# =============================================================================

class GeneratedCode(BaseModel):
    """Generated strategy code from Coder Agent."""
    
    strategy_name: str
    strategy_version: str
    
    # Generated files (content as strings)
    config_yaml: str = Field(default="")
    scanner_py: str = Field(default="")
    engine_py: str = Field(default="")
    monitor_py: str = Field(default="")
    tests_py: str = Field(default="")
    
    # Validation
    is_valid: bool = Field(default=False)
    validation_errors: list[str] = Field(default_factory=list)
    
    # Metadata
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    hypothesis_summary: str = Field(default="")


# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

CODER_SYSTEM_PROMPT = """You are a Python developer for Nexus 2, a trading automation platform.
You generate production-quality code following existing patterns.

CONSTRAINTS:
- Follow Nexus2 service patterns exactly
- Use Pydantic for all data models
- Include type hints on all functions
- Write pytest-compatible unit tests
- Code must be syntactically valid Python

ARCHITECTURE:
Nexus2 strategies follow a 3-tier architecture:
1. Scanner: Signal discovery (finds candidates matching criteria)
2. Engine: Entry detection (watches candidates, triggers entries)
3. Monitor: Position management (stops, exits, scales)

OUTPUT FORMAT:
Always respond with valid JSON containing these keys:
{
  "config": "YAML content as string",
  "scanner": "Python code as string",
  "engine": "Python code as string", 
  "monitor": "Python code as string",
  "tests": "Python test code as string"
}"""


def build_coder_prompt(
    hypothesis: Dict[str, Any],
    base_strategy_config: str,
    base_scanner_example: str = "",
) -> str:
    """Build the prompt for the Coder Agent."""
    
    prompt_parts = [
        "HYPOTHESIS TO IMPLEMENT:",
        f"- Change: {hypothesis.get('hypothesis', 'Unknown')}",
        f"- Rationale: {hypothesis.get('rationale', '')}",
        f"- Parameter Changes: {json.dumps(hypothesis.get('parameter_changes', {}))}",
        "",
        "BASE STRATEGY CONFIG (modify this):",
        "```yaml",
        base_strategy_config,
        "```",
        "",
    ]
    
    if base_scanner_example:
        prompt_parts.extend([
            "EXAMPLE SCANNER PATTERN (follow this structure):",
            "```python",
            base_scanner_example,
            "```",
            "",
        ])
    
    prompt_parts.extend([
        "TASK:",
        "Generate a complete strategy implementation based on the hypothesis.",
        "Apply the parameter_changes to the config.",
        "Generate scanner, engine, and monitor code that enforces these changes.",
        "Include unit tests that verify the changes work correctly.",
        "",
        "Respond with valid JSON containing: config, scanner, engine, monitor, tests",
    ])
    
    return "\n".join(prompt_parts)


# =============================================================================
# CODER AGENT
# =============================================================================

class CoderAgent:
    """LLM-powered code generation agent.
    
    Uses Gemini to generate strategy code from hypotheses.
    """
    
    def __init__(self):
        self._client = None
    
    def _get_client(self):
        """Lazy-load Gemini client.
        
        Uses GEMINI_LAB_KEY if available, falls back to GEMINI_API_KEY.
        """
        if self._client is None:
            try:
                from dotenv import load_dotenv
                load_dotenv()
                import os
                from google import genai
                
                # Prefer dedicated lab key, fall back to shared key
                api_key = os.environ.get("GEMINI_LAB_KEY") or os.environ.get("GEMINI_API_KEY")
                if not api_key:
                    raise ValueError("GEMINI_LAB_KEY or GEMINI_API_KEY not set")
                
                self._client = genai.Client(api_key=api_key)
                logger.info(f"[CoderAgent] Using {'GEMINI_LAB_KEY' if os.environ.get('GEMINI_LAB_KEY') else 'GEMINI_API_KEY'}")
            except Exception as e:
                logger.error(f"[CoderAgent] Failed to init Gemini client: {e}")
                raise
        return self._client
    
    def generate(
        self,
        hypothesis: Dict[str, Any],
        base_config: str,
        strategy_name: str = "lab_experiment",
        strategy_version: str = "1.0.0",
    ) -> GeneratedCode:
        """Generate strategy code from a hypothesis.
        
        Args:
            hypothesis: Hypothesis dict from ResearcherAgent
            base_config: Base strategy YAML config to modify
            strategy_name: Name for generated strategy
            strategy_version: Version for generated strategy
            
        Returns:
            GeneratedCode with all generated files
        """
        logger.info(f"[CoderAgent] Generating code for {strategy_name} v{strategy_version}")
        
        user_prompt = build_coder_prompt(hypothesis, base_config)
        
        try:
            client = self._get_client()
            
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[
                    {"role": "user", "parts": [{"text": CODER_SYSTEM_PROMPT}]},
                    {"role": "model", "parts": [{"text": "I understand. I will generate complete, valid Python code following Nexus2 patterns. I will respond with JSON containing config, scanner, engine, monitor, and tests."}]},
                    {"role": "user", "parts": [{"text": user_prompt}]},
                ],
            )
            
            # Extract and parse JSON with robust error handling
            response_text = response.text.strip()
            data = self._extract_json(response_text)
            
            if data is None:
                return GeneratedCode(
                    strategy_name=strategy_name,
                    strategy_version=strategy_version,
                    is_valid=False,
                    validation_errors=["Failed to extract valid JSON from response"],
                )
            
            result = GeneratedCode(
                strategy_name=strategy_name,
                strategy_version=strategy_version,
                config_yaml=data.get("config", ""),
                scanner_py=data.get("scanner", ""),
                engine_py=data.get("engine", ""),
                monitor_py=data.get("monitor", ""),
                tests_py=data.get("tests", ""),
                hypothesis_summary=hypothesis.get("hypothesis", ""),
            )
            
            # Validate the generated code
            result = self.validate(result)
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"[CoderAgent] Failed to parse response: {e}")
            return GeneratedCode(
                strategy_name=strategy_name,
                strategy_version=strategy_version,
                is_valid=False,
                validation_errors=[f"JSON parse error: {e}"],
            )
        except Exception as e:
            logger.error(f"[CoderAgent] Error: {e}")
            return GeneratedCode(
                strategy_name=strategy_name,
                strategy_version=strategy_version,
                is_valid=False,
                validation_errors=[f"Generation error: {e}"],
            )
    
    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON from LLM response with robust error handling.
        
        Handles:
        - Markdown code blocks (```json ... ```)
        - Invalid escape sequences from Gemini
        - Nested JSON structures
        
        Args:
            text: Raw response text from LLM
            
        Returns:
            Parsed dict or None if extraction fails
        """
        import re
        
        # Method 1: Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.debug(f"[CoderAgent] Direct parse failed: {e}")
        
        # Method 2: Extract from markdown code blocks
        # Handle ```json ... ``` or ``` ... ```
        code_block_pattern = r'```(?:json)?\s*\n?([\s\S]*?)\n?```'
        matches = re.findall(code_block_pattern, text)
        
        for i, match in enumerate(matches):
            cleaned = self._sanitize_json(match.strip())
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                logger.debug(f"[CoderAgent] Code block {i} parse failed: {e}")
                continue
        
        # Method 3: Find JSON object in text
        # Look for { ... } pattern
        brace_pattern = r'\{[\s\S]*\}'
        brace_match = re.search(brace_pattern, text)
        
        if brace_match:
            cleaned = self._sanitize_json(brace_match.group())
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                logger.debug(f"[CoderAgent] Brace extraction failed: {e}")
        
        # All methods failed - log the response for debugging
        logger.warning(f"[CoderAgent] All JSON extraction methods failed. Response length: {len(text)} chars")
        logger.debug(f"[CoderAgent] First 500 chars: {text[:500]}")
        
        # Save failed response to file for analysis
        try:
            from pathlib import Path
            from datetime import datetime
            debug_dir = Path(__file__).parent / "debug_responses"
            debug_dir.mkdir(exist_ok=True)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            debug_file = debug_dir / f"failed_response_{timestamp}.txt"
            debug_file.write_text(text)
            logger.info(f"[CoderAgent] Saved failed response to {debug_file.name}")
        except Exception as e:
            logger.debug(f"[CoderAgent] Could not save debug file: {e}")
        
        return None
    
    def _sanitize_json(self, text: str) -> str:
        """Sanitize JSON string to fix common LLM escape issues.
        
        Fixes:
        - Python hex escapes (\\xNN) to JSON unicode (\\u00NN)
        - Invalid escape sequences like \\e, \\s, \\d, etc.
        - Raw unicode characters that may cause issues
        
        Args:
            text: Raw JSON string
            
        Returns:
            Sanitized JSON string
        """
        import re
        
        # Fix 1: Convert Python hex escapes (\xNN) to JSON unicode escapes (\u00NN)
        # e.g., \xE4 -> \u00E4
        def hex_to_unicode(match):
            hex_val = match.group(1)
            return f"\\u00{hex_val}"
        
        text = re.sub(r'\\x([0-9a-fA-F]{2})', hex_to_unicode, text)
        
        # Fix 2: Replace invalid escape sequences
        # JSON only allows: \", \\, \/, \b, \f, \n, \r, \t, \uXXXX
        # Replace other escapes with double backslash
        invalid_escapes = re.compile(r'\\(?!["\\/bfnrtu])')
        text = invalid_escapes.sub(r'\\\\', text)
        
        return text
    
    def validate(self, code: GeneratedCode) -> GeneratedCode:
        """Validate generated code for syntax errors.
        
        Args:
            code: GeneratedCode to validate
            
        Returns:
            Same GeneratedCode with is_valid and validation_errors populated
        """
        import ast
        
        errors = []
        
        # Validate Python files
        for name, content in [
            ("scanner.py", code.scanner_py),
            ("engine.py", code.engine_py),
            ("monitor.py", code.monitor_py),
            ("tests.py", code.tests_py),
        ]:
            if content:
                try:
                    ast.parse(content)
                except SyntaxError as e:
                    errors.append(f"{name}: Syntax error at line {e.lineno}: {e.msg}")
        
        # Validate YAML
        if code.config_yaml:
            try:
                import yaml
                yaml.safe_load(code.config_yaml)
            except Exception as e:
                errors.append(f"config.yaml: YAML parse error: {e}")
        
        code.is_valid = len(errors) == 0
        code.validation_errors = errors
        
        return code
    
    def save_to_disk(
        self,
        code: GeneratedCode,
        output_dir: Path,
    ) -> bool:
        """Save generated code to disk.
        
        Args:
            code: GeneratedCode to save
            output_dir: Directory to save files in
            
        Returns:
            True if saved successfully
        """
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            
            if code.config_yaml:
                (output_dir / "config.yaml").write_text(code.config_yaml)
            
            if code.scanner_py:
                (output_dir / "scanner.py").write_text(code.scanner_py)
            
            if code.engine_py:
                (output_dir / "engine.py").write_text(code.engine_py)
            
            if code.monitor_py:
                (output_dir / "monitor.py").write_text(code.monitor_py)
            
            if code.tests_py:
                (output_dir / "test_strategy.py").write_text(code.tests_py)
            
            logger.info(f"[CoderAgent] Saved code to {output_dir}")
            return True
            
        except Exception as e:
            logger.error(f"[CoderAgent] Failed to save code: {e}")
            return False


# Singleton
_agent: Optional[CoderAgent] = None


def get_coder_agent() -> CoderAgent:
    """Get the singleton coder agent."""
    global _agent
    if _agent is None:
        _agent = CoderAgent()
    return _agent
