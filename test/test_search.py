import re


class_name = "abc"
class_name_pattern = r'[a-zA-Z_][a-zA-Z0-9_]*'
if not bool(re.search(class_name_pattern, class_name)):
    print("yes")
else:
    print("no")
