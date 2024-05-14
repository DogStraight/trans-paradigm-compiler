import random
import string
from faker import Faker

# 初始化faker对象
fake = Faker()

# 生成一个随机字符串作为键


def generate_random_key(length: int = 10):
    return ''.join(random.choices(
        string.ascii_letters + string.digits, k=length))

# 生成一个包含随机元素的字典


def generate_random_dict(num_items: int = 5) -> dict[str, str | int]:
    random_dict: dict[str, str | int] = {}
    for _ in range(num_items):
        key: str = generate_random_key()
        # 随机选择是生成一个整数还是文本作为值
        value: str | int = random.choice(
            [fake.text(), random.randint(1, 1000)])
        random_dict[key] = value
    return random_dict


# 生成一个包含5个随机键值对的字典
random_dictionary = generate_random_dict(5)

# for key in random_dictionary:
#     print(key)

for value in random_dictionary.values():
    print(value)
