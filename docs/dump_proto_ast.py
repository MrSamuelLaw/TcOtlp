"""Parse all OpenTelemetry .proto files and dump their ASTs to JSON."""

import dataclasses
import enum
import json
from pathlib import Path

from proto_schema_parser.parser import Parser

enum_base = enum.Enum

PROTO_ROOT = Path("opentelemetry-proto")


def ast_to_dict(node):
    """Recursively convert AST nodes to JSON-serializable dicts."""
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        result = {"_type": type(node).__name__}
        for f in dataclasses.fields(node):
            result[f.name] = ast_to_dict(getattr(node, f.name))
        return result
    elif isinstance(node, list):
        return [ast_to_dict(item) for item in node]
    elif isinstance(node, tuple):
        return [ast_to_dict(item) for item in node]
    elif isinstance(node, enum_base):
        return node.name
    elif node is None or isinstance(node, (str, int, float, bool)):
        return node
    else:
        return str(node)


parser = Parser()
proto_files = sorted(PROTO_ROOT.rglob("*.proto"))

output = {}
for proto_file in proto_files:
    rel = str(proto_file.relative_to(PROTO_ROOT))
    print(f"Parsing: {rel}")
    text = proto_file.read_text(encoding="utf-8")
    try:
        ast = parser.parse(text)
        output[rel] = ast_to_dict(ast)
    except Exception as e:
        output[rel] = {"_error": str(e)}
        print(f"  ERROR: {e}")

out_path = Path("proto_ast.json")
out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
print(f"\nWrote {out_path} ({out_path.stat().st_size:,} bytes)")
