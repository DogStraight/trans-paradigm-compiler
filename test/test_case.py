a: str = "d"
match a:
    case "ab" | "abc" | "cd":
        print("yes")
    case _:
        print("no")
