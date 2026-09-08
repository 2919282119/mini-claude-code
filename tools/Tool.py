class Tool:
    def __init__(self, name, description, parameters, function, permission_level="READ"):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.function = function
        self.permission_level = permission_level

    def execute(self, **kwargs):
        return self.function(**kwargs)

    def to_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }