"""Typed argument boundaries before planning acceptance and tool dispatch."""
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Arguments(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ListFiles(Arguments):
    path: str = '.'
    pattern: str = '*'
    limit: int = Field(default=100, ge=1, le=300)


class ReadFile(Arguments):
    path: str
    start_line: int = Field(default=1, ge=1)
    max_lines: int = Field(default=200, ge=1, le=1000)


class SearchFiles(Arguments):
    path: str = '.'
    query: str = Field(min_length=1)
    limit: int = Field(default=30, ge=1, le=100)


class WriteFile(Arguments):
    path: str
    content: str
    expected_sha256: str | None = None


class Shell(Arguments):
    command: list[str] = Field(min_length=1)
    cwd: str = '.'


class RepairCommand(Shell):
    command: list[str] = Field(min_length=1, max_length=32)
    failure: dict[str, Any]


class FetchURL(Arguments):
    url: str


class MCP(Arguments):
    server: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class DiscoverTools(Arguments):
    query: str = Field(default='', max_length=200)
    server: str = Field(default='', max_length=1000)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=10, ge=1, le=20)


class InspectTool(Arguments):
    server: str = Field(min_length=1, max_length=1000)
    tool: str = Field(min_length=1, max_length=1000)
    offset: int = Field(default=0, ge=0)
    max_chars: int = Field(default=12000, ge=1, le=20000)
    expected_sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')


class InspectImage(Arguments):
    source: str = Field(min_length=1, max_length=4096)
    question: str = Field(min_length=1, max_length=4000)


class Generate(Arguments):
    prompt: str = Field(min_length=1)


class Choose(Arguments):
    question: str = Field(min_length=1)
    options: dict[str, Any] | list[Any]
    values: dict[str, Any] = Field(default_factory=dict)


class ReadEvidence(Arguments):
    id: str
    offset: int = Field(default=0, ge=0)
    max_chars: int = Field(default=12000, ge=1, le=20000)


class SearchEvidence(Arguments):
    query: str = Field(default='', max_length=500)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=10, ge=1, le=20)


class Predicate(Arguments):
    column: str
    op: Literal['eq', 'ne', 'gt', 'gte', 'lt', 'lte']
    value: Any


class QueryTable(Arguments):
    path: str
    operation: Literal['sum', 'mean', 'count', 'min', 'max']
    group_by: str | None = None
    value_column: str | None = None
    filters: list[Predicate] = Field(default_factory=list, max_length=16)


class ListSkills(Arguments):
    query: str = Field(default='', max_length=200)


class LoadSkill(Arguments):
    name: str = Field(min_length=1, max_length=64)
    reference: str | None = Field(default=None, max_length=500)


CONTRACTS = {
    'discover_tools': DiscoverTools, 'inspect_tool': InspectTool,
    'inspect_image': InspectImage,
    'list_skills': ListSkills, 'load_skill': LoadSkill,
    'list_files': ListFiles, 'read_file': ReadFile, 'search_files': SearchFiles,
    'write_file': WriteFile, 'shell': Shell, 'repair_command': RepairCommand,
    'fetch_url': FetchURL, 'mcp': MCP, 'generate': Generate, 'research': Generate,
    'choose': Choose, 'read_evidence': ReadEvidence, 'search_evidence': SearchEvidence,
    'query_table': QueryTable,
}
REFERENCE = re.compile(r'^\$\{[a-z][a-z0-9_]*(?:\.[A-Za-z0-9_]+)*\}$')


def deferred_at(arguments, location):
    current = arguments
    for part in (*location, None):
        if isinstance(current, str) and REFERENCE.fullmatch(current):
            return True
        if part is None:
            break
        try:
            current = current[part]
        except (KeyError, TypeError, IndexError):
            return False
    return False


def validate_arguments(tool, arguments, *, allow_references=False):
    if tool not in CONTRACTS:
        raise ValueError(f'Unknown tool: {tool}')
    try:
        return CONTRACTS[tool].model_validate(arguments).model_dump()
    except ValidationError as error:
        errors = error.errors(include_input=False, include_url=False)
        if allow_references:
            errors = [e for e in errors if e['type'] in {'missing', 'extra_forbidden'} or not deferred_at(arguments, e['loc'])]
        if errors:
            description = '; '.join('.'.join(map(str, e['loc'])) + ': ' + e['msg'] for e in errors)
            raise ValueError(f'Invalid {tool} arguments: {description}') from None
        # Preserve references verbatim; they must pass full validation after binding.
        return arguments
