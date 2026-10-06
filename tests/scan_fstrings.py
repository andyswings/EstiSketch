import os
import tokenize

def scan_file(filepath):
    with open(filepath, 'rb') as f:
        try:
            tokens = list(tokenize.tokenize(f.readline))
        except tokenize.TokenError:
            print(f"TokenError in {filepath}")
            return

    for tok in tokens:
        if tok.type == tokenize.STRING:
            s = tok.string
            # Check if it is an f-string
            if s.lower().startswith('f') or s.lower().startswith('rf') or s.lower().startswith('fr'):
                # Check for newlines within the string content
                if '\n' in s:
                    # If it uses triple quotes, it's allowed to have newlines
                    if s.lower().startswith('f"""') or s.lower().startswith("f'''") or \
                       s.lower().startswith('rf"""') or s.lower().startswith("rf'''") or \
                       s.lower().startswith('fr"""') or s.lower().startswith("fr'''"):
                        continue
                    
                    # If it's a single-quoted string with a newline, it's likely the issue
                    # (Python < 3.12 doesn't allow newlines inside f-string expressions 
                    # unless triple-quoted, and doesn't allow unescaped newlines in single quotes at all)
                    print(f"Found suspicious f-string in {filepath} at line {tok.start[0]}:")
                    print(f"  {s[:50]}...")
                    print("-" * 40)

def main():
    root_dir = "src/EstiSketch"
    print(f"Scanning {root_dir} for potential f-string issues (Python < 3.12 compatibility)...")
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith(".py"):
                filepath = os.path.join(dirpath, filename)
                scan_file(filepath)

if __name__ == "__main__":
    main()
