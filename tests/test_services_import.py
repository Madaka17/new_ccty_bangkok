"""Importing backend.services must not start any background job; services.start() does.

The real module loads YOLO and starts threads on import, so it is read with ast instead of imported."""
import ast
from pathlib import Path

SERVICES = Path(__file__).resolve().parent.parent / "backend" / "services.py"
DEF_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _module_level_calls(tree):
    """Calls that run at import: everything outside a function body."""
    found = []
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, DEF_NODES):
            continue
        if isinstance(node, ast.Call):
            found.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return found


def _start_calls(calls):
    return [c.func.value.id for c in calls
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "start" and isinstance(c.func.value, ast.Name)]


def test_no_module_level_start_call():
    tree = ast.parse(SERVICES.read_text(encoding="utf-8"))
    assert _start_calls(_module_level_calls(tree)) == []


def test_start_function_starts_survey_then_camera_health():
    tree = ast.parse(SERVICES.read_text(encoding="utf-8"))
    start_def = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "start")
    assert _start_calls(list(ast.walk(start_def)))[:2] == ["survey", "camera_health"]
