class Signal():
    is_input: bool = True  # input for now
    is_duplex: bool = False
    width: str = "1"
    name: str = ""
    turns: str = "1"
    # name must be declared

    def __init__(
        self, name: str, width: str = "1", is_input: bool = True,
        is_duplex: bool = False, turns: str = "1"
    ) -> None:
        self.name = name
        self.width = width
        self.is_duplex = is_duplex
        self.is_input = is_input
        self.turns = turns
        


class Interface:
    type: str = ""
    speed: str = "low"
    member: list[Signal] = []
    is_ref_sys_clk: bool = True
    alias: str = ""

    def __init__(
            self, *member: Signal, type: str,
            speed: str = "low", is_ref_sys_clk=True, alias: str = "") -> None:
        self.type = type
        self.speed = speed
        self.is_ref_sys_clk = is_ref_sys_clk
        self.alias = alias
        self.member = [member[_] for _ in range(len(member))]

    def port_list(self, is_master: bool = True) -> str:
        # character
        blank: str = " "
        underline: str = "_"
        comma: str = ","
        # string
        port_list_content: str = ""

        # start point
        port_list_content +=\
            f"/* port_list : interface {self.type} "\
            f"alias={self.alias} speed={self.speed} start */\n"

        # port_list_content
        for member in self.member:
            # direction
            port_list_content \
                += "inout" \
                if member.is_duplex \
                else "input" \
                if (member.is_input and is_master) \
                or (not member.is_input and not is_master)\
                else "output"
            port_list_content += blank
            # width
            if member.width != "1":
                port_list_content += f"[({member.width}-1):0]" + blank
            # name
            port_list_content += member.name + underline + self.alias
            # turns
            if member.turns != "1":
                port_list_content += blank + f"[({member.turns}-1):0]"
            # comma
            port_list_content += comma + "\n"

         # end point
        port_list_content += \
            f"/* port_list : interface "\
            f"{self.type} alias={self.alias} end */\n"
        return port_list_content

    def instance(self, connection: str) -> str:
        instance_content: str = ""

        


class SpiInterface(Interface):
    # description
    speed: str = "50MHz"

    # mode ctl
    clk_polar: bool = 0
    pha_polar: bool = 0

    def __init__(
        self, alias: str, speed: str = "auto",
            is_ref_sys_clk=False) -> None:
        self.speed = speed
        self.is_ref_sys_clk = is_ref_sys_clk
        # as spi master
        spi_clk:  Signal = Signal(name="spi_clk", is_input=False)
        spi_slc:  Signal = Signal(name="spi_slc", is_input=False)
        spi_miso: Signal = Signal(name="spi_miso")
        spi_mosi: Signal = Signal(name="spi_mosi", is_input=False)
        super().__init__(
            spi_clk, spi_slc, spi_miso, spi_mosi,
            alias=alias, type="spi",
            speed=self.speed, is_ref_sys_clk=is_ref_sys_clk)

    


if __name__ == "__main__":
    spi_interface_1 = SpiInterface(alias="test2")
    spi_interface_2 = SpiInterface(alias="test1")
    print(spi_interface_1.port_list(is_master=False))
    print(spi_interface_1.speed)
