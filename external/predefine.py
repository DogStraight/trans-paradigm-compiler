
# encoding
encoding: str = 'utf-8'

# regex
regex_header_exist: str = "file header"  
regex_header_content: str = r"/\*\n?\{([\s\S]*)\}\n? *\*/\n?"

# to match file name
regex_file_name: str = r"([^\\]+)$"

# to match module name
regex_module_name: str = r"\n?\s*module\s*([a-zA-Z0-9_]{1,}){1,}\s*#?\s*\("

# time format
time_format_str: str = "%Y_%m_%d %p %I_%M_%S"  


# read file
def fread(file: str, encoding=encoding) -> str:
    with open(file=file, encoding=encoding, mode="r") as f:
        return f.read()


# write file
def fwrite(file: str, content: str, encoding=encoding, mode="w") -> int:
    """  """
    with open(file=file, encoding=encoding, mode=mode) as f:
        return f.write(content)
