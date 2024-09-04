def get_type() -> list[str]:
    from os import walk
    _, types, _ = next(walk("./grammar/type"))
    return types


if __name__ == "__main__":
    print(get_type())
