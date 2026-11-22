from PySide6.QtWidgets import QWidget, QStackedLayout, QGraphicsOpacityEffect
from PySide6.QtCore import QPropertyAnimation, QParallelAnimationGroup, QEasingCurve


class AnimatedStack(QWidget):
    """
    Component thay thế QStackedWidget, cho phép CrossFade mượt mà giữa các page
    và tự động tắt QGraphicsOpacityEffect khi rảnh để tránh chi phí dựng hình offscreen.
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        self.layout = QStackedLayout(self)
        self.layout.setStackingMode(QStackedLayout.StackAll)

        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.finished.connect(self._on_transition_finished)

        self.current_index = -1
        self.widgets = []
        self._is_transitioning = False

    def addWidget(self, widget: QWidget):
        self.layout.addWidget(widget)
        self.widgets.append(widget)

        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(1.0 if self.current_index == -1 else 0.0)
        effect.setEnabled(False)
        widget.setGraphicsEffect(effect)

        if self.current_index == -1:
            self.current_index = 0
            widget.show()
        else:
            widget.hide()

        return len(self.widgets) - 1

    def setCurrentIndex(self, index: int, duration: int = 180):
        if index < 0 or index >= len(self.widgets):
            return

        if self.anim_group.state() == QParallelAnimationGroup.Running:
            if index == self.target_index_cache:
                return
            self.anim_group.stop()
            self._force_finish_transition()

        if index == self.current_index:
            return

        current_widget = self.widgets[self.current_index]
        target_widget = self.widgets[index]

        if duration <= 0 or not self.isVisible():
            current_eff = current_widget.graphicsEffect()
            if current_eff:
                current_eff.setEnabled(False)
            current_widget.hide()
            target_eff = target_widget.graphicsEffect()
            if target_eff:
                target_eff.setOpacity(1.0)
                target_eff.setEnabled(False)
            target_widget.show()
            target_widget.raise_()
            self.current_index = index
            self.target_index_cache = index
            self._is_transitioning = False
            return

        self._is_transitioning = True

        current_effect = current_widget.graphicsEffect()
        target_effect = target_widget.graphicsEffect()
        if current_effect:
            current_effect.setOpacity(1.0)
            current_effect.setEnabled(True)
        if target_effect:
            target_effect.setOpacity(0.0)
            target_effect.setEnabled(True)

        target_widget.show()
        target_widget.raise_()

        self.anim_group.clear()

        anim_out = QPropertyAnimation(current_effect, b"opacity")
        anim_out.setDuration(duration)
        anim_out.setStartValue(1.0)
        anim_out.setEndValue(0.0)
        anim_out.setEasingCurve(QEasingCurve.OutCubic)
        self.anim_group.addAnimation(anim_out)

        anim_in = QPropertyAnimation(target_effect, b"opacity")
        anim_in.setDuration(duration)
        anim_in.setStartValue(0.0)
        anim_in.setEndValue(1.0)
        anim_in.setEasingCurve(QEasingCurve.OutCubic)
        self.anim_group.addAnimation(anim_in)

        self.target_index_cache = index
        self.anim_group.start()

    def _on_transition_finished(self):
        self._force_finish_transition()

    def _force_finish_transition(self):
        if not self._is_transitioning:
            return

        old_widget = self.widgets[self.current_index]
        old_eff = old_widget.graphicsEffect()
        if old_eff:
            old_eff.setEnabled(False)
        old_widget.hide()

        self.current_index = self.target_index_cache
        target_widget = self.widgets[self.current_index]
        target_eff = target_widget.graphicsEffect()
        if target_eff:
            target_eff.setOpacity(1.0)
            target_eff.setEnabled(False)

        self._is_transitioning = False

    def currentWidget(self):
        idx = self.currentIndex()
        if 0 <= idx < len(self.widgets):
            return self.widgets[idx]
        return None

    def count(self) -> int:
        return len(self.widgets)

    def currentIndex(self) -> int:
        if getattr(self, "_is_transitioning", False) and hasattr(self, "target_index_cache"):
            return self.target_index_cache
        return self.current_index
