"""AST extractor — uses tree-sitter to extract changed function signatures and exports."""

from pathlib import Path

import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspython.language())
JS_LANGUAGE = Language(tsjavascript.language())
TS_LANGUAGE = Language(tstypescript.language_typescript())
TSX_LANGUAGE = Language(tstypescript.language_tsx())

_PARSERS: dict[str, Parser] = {}


def _get_parser(ext: str) -> Parser | None:
    """Return a cached Parser for the given file extension, or None if unsupported."""
    if ext in _PARSERS:
        return _PARSERS[ext]

    lang_map = {
        ".py": PY_LANGUAGE,
        ".js": JS_LANGUAGE,
        ".mjs": JS_LANGUAGE,
        ".cjs": JS_LANGUAGE,
        ".ts": TS_LANGUAGE,
        ".tsx": TSX_LANGUAGE,
    }

    lang = lang_map.get(ext)
    if lang is None:
        return None

    parser = Parser(lang)
    _PARSERS[ext] = parser
    return parser


def extract_definitions(file_path: str, repo_path: str = ".") -> dict:
    """
    Parse a source file and extract top-level function/class definitions and exports.

    Returns:
        {
            "functions": ["func_name", ...],
            "classes": ["ClassName", ...],
            "exports": ["exported_name", ...],
        }
    """
    path = Path(repo_path) / file_path
    ext = path.suffix.lower()

    parser = _get_parser(ext)
    if parser is None:
        return {"functions": [], "classes": [], "exports": []}

    try:
        source = path.read_bytes()
    except FileNotFoundError:
        return {"functions": [], "classes": [], "exports": []}

    tree = parser.parse(source)
    root = tree.root_node

    if ext == ".py":
        return _extract_python(root)
    return _extract_js_ts(root)


def _node_name(node, source_bytes: bytes) -> str:
    """Extract the name identifier child of a node."""
    for child in node.children:
        if child.type == "identifier":
            return source_bytes[child.start_byte:child.end_byte].decode(errors="replace")
    return ""


def _extract_python(root) -> dict:
    source = root.text
    functions, classes = [], []

    def walk(node):
        if node.type == "function_definition":
            name = _node_name(node, source)
            if name:
                functions.append(name)
        elif node.type == "class_definition":
            name = _node_name(node, source)
            if name:
                classes.append(name)
        for child in node.children:
            walk(child)

    walk(root)
    return {"functions": functions, "classes": classes, "exports": []}


def _extract_js_ts(root) -> dict:
    source = root.text
    functions, classes, exports = [], [], []

    def walk(node):
        t = node.type

        if t == "function_declaration":
            name = _node_name(node, source)
            if name:
                functions.append(name)

        elif t == "class_declaration":
            name = _node_name(node, source)
            if name:
                classes.append(name)

        elif t == "export_statement":
            # Collect identifiers directly exported
            for child in node.children:
                if child.type in ("function_declaration", "class_declaration"):
                    name = _node_name(child, source)
                    if name:
                        exports.append(name)
                elif child.type == "export_clause":
                    for spec in child.children:
                        if spec.type == "export_specifier":
                            name = _node_name(spec, source)
                            if name:
                                exports.append(name)

        elif t == "lexical_declaration":
            # const foo = () => {} or const foo = function() {}
            for child in node.children:
                if child.type == "variable_declarator":
                    name = _node_name(child, source)
                    if name:
                        functions.append(name)

        for child in node.children:
            walk(child)

    walk(root)
    return {"functions": functions, "classes": classes, "exports": exports}
