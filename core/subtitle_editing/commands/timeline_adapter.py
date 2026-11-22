from PySide6.QtGui import QUndoCommand


class TimelineCommandAdapter(QUndoCommand):
    """Bridges legacy timeline commands into the application's QUndoStack."""
    def __init__(self, command, after_mutate=None):
        super().__init__(getattr(command, "description", "Timeline edit"))
        self.command = command
        self._after_mutate = after_mutate
        self._executed = False

    def redo(self):
        if self._executed:
            self.command.redo()
        else:
            if hasattr(self.command, "execute"):
                self.command.execute(context=None)
            else:
                self.command.redo()
            self._executed = True
        if callable(self._after_mutate):
            self._after_mutate()

    def undo(self):
        self.command.undo()
        if callable(self._after_mutate):
            self._after_mutate()
