def gc_input_check():
    pass


class NameSpaceItem:
    def __init__(self, name: str, value):
        self.name = name
        self.value = value   # value can be any type

    def __str__(self):
        return f"{self.name}: {self.value}"


class NameSpaceCreator:
    def __init__(self, space_name: str):
        self.space_name = space_name
        self.namespace = []

    def show_space_name(self):
        return self.space_name

    def search_name(self, name: str):
        for item in self.namespace:
            if item.name == name:
                return item
        return None

    def add_name(self, name: str, value):
        item = self.search_name(name)
        if item is None:
            self.namespace.append(NameSpaceItem(name, value))
        else:
            item.value = value

    def remove_name(self, name: str):
        item = self.search_name(name)
        if item is not None:
            self.namespace.remove(item)

    def dump(self):
        pass


class VCodeGenerator:

    def __init__(self, gc_template_set_path: str):
        # gc template is an dir
        self.namespace = []
        pass

    def load_module(self, module_name: str):
        # module is a file
        pass

    def unload_module(self, module_name: str):
        pass

    def refresh_namespace(self):
        pass

    def generate_code(self, code_type: str, code_content: str):
        pass

    def dump_namespace(self):
        pass
