from parsers import python_parser, javascript_parser, java_parser, c_parser
import os

EXTENSION_MAP = {
    ".py": ("python", python_parser),
    ".js": ("javascript", javascript_parser),
    ".jsx": ("javascript", javascript_parser),
    ".ts": ("javascript", javascript_parser),
    ".tsx": ("javascript", javascript_parser),
    ".java": ("java", java_parser),
    ".c": ("c", c_parser),
    ".cpp": ("c", c_parser),
    ".h": ("c", c_parser),
    ".hpp": ("c", c_parser),
}

def get_parser(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    return EXTENSION_MAP.get(ext, (None, None))

def parse_file(file_path):
    language, parser = get_parser(file_path)
    if parser:
        return language, parser.parse(file_path)
    return None, []
