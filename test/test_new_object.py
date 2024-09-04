class Aob:
    pass


class Aob_b:
    def __init__(self) -> None:
        self.inner_list: list[Aob] = []
        pass

    def b(self):
        Aob_ins = Aob()
        self.inner_list.append(Aob_ins)
        print(id(Aob_ins))
        pass
    pass


if __name__ == "__main__":
    Aob_b_ins = Aob_b()
    Aob_b_ins.b()
    Aob_b_ins.b()
    print(Aob_b_ins.inner_list)
