class BaseAgent:
    def __init__(self, name):
            self.name = name

                def act(self):
                        raise NotImplementedError("This method should be overridden.")

                            def __repr__(self):
                                    return f"<BaseAgent: {self.name}>""
