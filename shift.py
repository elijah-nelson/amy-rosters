class Shift:

    def __init__(self):
        self.start = None
        self.end = None
        self.position = None

    def __str__(self):
        return f"{self.start}-{self.end}: {self.position}"