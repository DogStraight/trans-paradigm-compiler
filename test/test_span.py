import re

text = "Hello, this is a test string."
pattern = re.compile(r"test")
match = pattern.search(text)
print(f"match:{match}")
if match:
    start, end = match.span()
    print(f"Found match at positions {start} to {end-1}: {match.group()}")
