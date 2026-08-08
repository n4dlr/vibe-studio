"""ThreadManager — manages background QThread task execution for non-blocking GUI operations."""
from __future__ import annotations

from typing import Any, Callable
from PySide6.QtCore import QObject, QThread, Signal, Slot


class WorkerTask(QObject):
    finished = Signal(object)
    error = Signal(Exception)
    progress = Signal(str)

    def __init__(self, func: Callable[..., Any], *args: Any, **kwargs: Any):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    @Slot()
    def run(self) -> None:
        try:
            res = self.func(*self.args, **self.kwargs)
            self.finished.emit(res)
        except Exception as exc:
            self.error.emit(exc)


class ThreadManager(QObject):
    """Central manager for executing heavy blocking operations in background QThreads."""

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._threads: list[tuple[QThread, WorkerTask]] = []

    def run_in_background(
        self,
        func: Callable[..., Any],
        *args: Any,
        on_finished: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        **kwargs: Any,
    ) -> tuple[QThread, WorkerTask]:
        thread = QThread(self)
        worker = WorkerTask(func, *args, **kwargs)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)

        if on_finished:
            worker.finished.connect(on_finished)
        if on_error:
            worker.error.connect(on_error)

        def _cleanup():
            thread.quit()
            worker.deleteLater()
            thread.deleteLater()
            self._threads = [(t, w) for t, w in self._threads if t != thread]

        worker.finished.connect(_cleanup)
        worker.error.connect(_cleanup)

        self._threads.append((thread, worker))
        thread.start()
        return thread, worker

    def cancel_all(self) -> None:
        for thread, _ in list(self._threads):
            if thread.isRunning():
                thread.quit()
                thread.wait(500)
        self._threads.clear()
