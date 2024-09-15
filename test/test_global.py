def test_global():
    global x
    x = 10


test_global()
print(x)  # 10
