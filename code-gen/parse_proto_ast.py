"""Parse all OpenTelemetry .proto files and return AST as a dict and can optionally dump to json"""
import argparse
import dataclasses
import enum
import json
from pathlib import Path

from proto_schema_parser.parser import Parser

enum_base = enum.Enum

PROTO_ROOT = Path(__file__).parent / "opentelemetry-proto"

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

def parse_proto() -> dict:
    """Parse all .proto files and return the AST as a dict."""
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

    return output


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="Parse proto files to AST")
    arg_parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for proto_ast.json (omit to skip writing)",
    )
    args = arg_parser.parse_args()

    ast = parse_proto()

    if args.output_dir is not None:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "proto_ast.json"
        out_path.write_text(json.dumps(ast, indent=2), encoding="utf-8")
        print(f"\nWrote {out_path} ({out_path.stat().st_size:,} bytes)")
    else:
        print(f"\nParsed {len(ast)} proto files (use --output-dir to write JSON)")
