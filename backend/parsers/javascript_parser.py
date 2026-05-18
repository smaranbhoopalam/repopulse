import re

def parse(file_path):
    imports = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Match ES6 imports: import X from 'Y'
        es6_pattern = re.compile(r"import\s+.*?\s+from\s+['\"](.*?)['\"]")
        for match in es6_pattern.finditer(content):
            imports.append(match.group(1))
            
        # Match ES6 side-effect imports: import 'X'
        es6_simple = re.compile(r"import\s+['\"](.*?)['\"]")
        for match in es6_simple.finditer(content):
            imports.append(match.group(1))
            
        # Match CommonJS: require('X')
        cjs_pattern = re.compile(r"require\(['\"](.*?)['\"]\)")
        for match in cjs_pattern.finditer(content):
            imports.append(match.group(1))
    except Exception:
        pass
    return imports
