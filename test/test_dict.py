test_dict: dict = {
    "frist_key": "a",
    "frisu_key": "b",
    "frisv_key": "c",
    "frisw_key": "d",
}

test_a = "a"

for item in test_dict:
    if test_dict[item] == test_a:
        print(item)
