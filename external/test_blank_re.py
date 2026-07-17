def fread(file: str, encoding="utf-8") -> str:
    with open(file=file, encoding=encoding, mode="r") as f:
        return f.read()


def fwrite(file: str, content: str, encoding="utf-8") -> int:
    with open(file=file, encoding=encoding, mode="w") as f:
        return f.write(content)


str = fread("test\\_test_indent.v")
print(str)
fwrite("test\\_test_indent.v", "")
