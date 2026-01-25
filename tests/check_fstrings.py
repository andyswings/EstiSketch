import os
import re

def check_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines):
        # Naive check: look for f-string start that doesn't close on the same line
        # This catches f" ... { \n
        
        # Check for single-quoted f-strings
        # Regex: f followed by " or ', then anything, but NOT ending with the same quote
        # We need to ignore lines that are logically continued with \
        
        stripped = line.strip()
        if not stripped:
            continue
            
        # If line starts an f-string
        # Patterns: f"...", f'...', rf"...", etc.
        # We care about cases where the string is OPEN at the end of the line
        
        # Simple heuristic: Count quotes?
        # If a line contains `f"` or `f'` but the count of `"` or `'` is odd?
        # No, that's too fragile (comments, escaped quotes).
        
        # Let's look for the specific pattern we've seen:
        # line ends with `{` or inside an expression?
        
        # actually, the error is "unterminated string literal"
        # because the line ends without closing the quote.
        
        matches = re.finditer(r'(^|[^a-zA-Z0-9_])(f|fr|rf)(["\'])', line)
        for m in matches:
            # We found a start of an f-string.
            # Check if it is a triple quote
            quote_char = m.group(3)
            start_idx = m.start(2)
            
            # Check if triple quote
            if line[m.end(3):].startswith(quote_char * 2):
                # Triple quote - ignore
                continue
                
            # It's a single quote f-string.
            # Does it close on this line?
            # Find the next quote_char that is not escaped
            rest_of_line = line[m.end(3):]
            
            # Simple parser to find closing quote
            idx = 0
            closed = False
            while idx < len(rest_of_line):
                char = rest_of_line[idx]
                if char == '\\':
                    idx += 2 # Skip next char
                    continue
                if char == quote_char:
                    closed = True
                    break
                idx += 1
            
            if not closed:
                # It's not closed! This is acceptable in Python 3.12 (multiline f-string)
                # but NOT in Python 3.11 for single-quoted strings (SyntaxError).
                print(f"{filepath}:{i+1}: Potential unclosed single-quoted f-string")
                print(f"  {line.strip()}")

def main():
    print("Scanning for single-quoted multiline f-strings...")
    for root, dirs, files in os.walk("src/EstiSketch"):
        for file in files:
            if file.endswith(".py"):
                check_file(os.path.join(root, file))

if __name__ == "__main__":
    main()
