class HaxAPIException(RuntimeError):
    def __init__(self, message: str):
        super().__init__()
        self.message = message


class HAConsistencyException(HaxAPIException):
    pass
