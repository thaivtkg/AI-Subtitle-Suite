import sys
from PySide6.QtCore import Qt, QTimer, QRectF, QObject, QEvent, QPoint
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QPen
from PySide6.QtWidgets import QWidget, QTabBar, QListWidget, QListView


class LiquidOverlayWidget(QWidget):
    """
    Overlay Kính lỏng (Liquid Glass Physics) cho các thành phần danh sách:
    - QListWidget / QListView
    - QTabBar
    Cung cấp hiệu ứng vệt kính lỏng đàn hồi theo mục đang chọn (Active)
    và hover pill nhẹ nhàng theo chuột.
    """

    def __init__(self, target):
        parent = target.viewport() if hasattr(target, "viewport") else target
        super().__init__(parent)
        self.target = target
        self._in_sync = False
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        # Active blob physics - khởi tạo trước mọi kết nối
        init_w = float(max(20, (self.parent().width() if self.parent() else 100) - 8))
        self._blob_y = -100.0
        self._blob_x = 4.0
        self._blob_w = init_w
        self._blob_h = 32.0
        self._target_y = -100.0
        self._velocity_y = 0.0

        # Hover state
        self._hover_y = -100.0
        self._hover_x = 4.0
        self._hover_w = init_w
        self._hover_h = 32.0
        self._hover_target_y = -100.0
        self._hover_alpha = 0.0

        # Kích hoạt mouse tracking
        self.target.setMouseTracking(True)
        if hasattr(self.target, "viewport") and self.target.viewport():
            self.target.viewport().setMouseTracking(True)
            self.target.viewport().installEventFilter(self)
        self.target.installEventFilter(self)

        # Hook scroll để giữ vị trí chính xác
        if hasattr(self.target, "verticalScrollBar") and self.target.verticalScrollBar():
            self.target.verticalScrollBar().valueChanged.connect(self._sync_geometry)
        if hasattr(self.target, "horizontalScrollBar") and self.target.horizontalScrollBar():
            self.target.horizontalScrollBar().valueChanged.connect(self._sync_geometry)

        # Hook selection change để cập nhật tức thì khi chuyển mục
        if hasattr(self.target, "currentItemChanged") and hasattr(self.target.currentItemChanged, "connect"):
            self.target.currentItemChanged.connect(lambda _c, _p: self._sync_active_target())
        if hasattr(self.target, "selectionModel") and self.target.selectionModel() and hasattr(self.target.selectionModel().currentChanged, "connect"):
            self.target.selectionModel().currentChanged.connect(lambda _c, _p: self._sync_active_target())

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_physics)
        self.timer.start(16)

        self._sync_geometry()
        self.raise_()

    def _sync_geometry(self):
        if getattr(self, "_in_sync", False) or not self.target or not self.parent():
            return
        self._in_sync = True
        try:
            pw, ph = self.parent().width(), self.parent().height()
            if self.width() != pw or self.height() != ph:
                self.setGeometry(0, 0, pw, ph)
            vp_w = float(pw)
            default_w = float(max(20, vp_w - 8))
            if not (hasattr(self.target, "currentItem") and self.target.currentItem()):
                self._blob_w = default_w
                self._blob_x = 4.0
            self._sync_active_target()
            self.raise_()
            self.update()
        finally:
            self._in_sync = False

    def _sync_active_target(self):
        if not self.target:
            return
        if isinstance(self.target, QTabBar):
            idx = self.target.currentIndex()
            if idx >= 0:
                rect = self.target.tabRect(idx)
                self._target_y = float(rect.center().x())
                self._blob_h = float(rect.width())
        elif hasattr(self.target, "currentItem"):
            item = self.target.currentItem()
            vp_w = float(self.parent().width()) if self.parent() else float(self.width())
            if item:
                rect = self.target.visualItemRect(item)
                if rect.isValid() and rect.height() > 0:
                    self._target_y = float(rect.center().y())
                    self._blob_h = float(rect.height())
                    rect_w = float(rect.width()) if rect.width() > 20 else vp_w
                    self._blob_w = float(max(20, rect_w - 8))
                    self._blob_x = float(rect.x() + 4) if rect.width() > 20 else 4.0
                    if self._blob_y < -50:
                        self._blob_y = self._target_y
            else:
                self._blob_w = float(max(20, vp_w - 8))
                self._blob_x = 4.0

    def _update_physics(self):
        if self.parent() and (self.width() != self.parent().width() or self.height() != self.parent().height()):
            self._sync_geometry()

        self._sync_active_target()

        # Spring physics cho active selection
        if self._target_y >= 0:
            spring_k = 0.22
            damping = 0.70
            force_y = (self._target_y - self._blob_y) * spring_k
            self._velocity_y = (self._velocity_y + force_y) * damping
            self._blob_y += self._velocity_y

        # Hover physics
        if self._hover_target_y >= 0:
            self._hover_y += (self._hover_target_y - self._hover_y) * 0.28
            self._hover_alpha += (40.0 - self._hover_alpha) * 0.22
        else:
            self._hover_alpha += (0.0 - self._hover_alpha) * 0.22

        if abs(self._velocity_y) > 0.1 or self._hover_alpha > 1 or abs(self._target_y - self._blob_y) > 0.5:
            self.update()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseMove:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            if isinstance(self.target, QTabBar):
                idx = self.target.tabAt(pos)
                if idx >= 0:
                    rect = self.target.tabRect(idx)
                    self._hover_target_y = float(rect.center().x())
                    self._hover_h = float(rect.width())
                else:
                    self._hover_target_y = -100.0
            elif hasattr(self.target, "itemAt"):
                item = self.target.itemAt(pos)
                if item and item != self.target.currentItem():
                    rect = self.target.visualItemRect(item)
                    self._hover_target_y = float(rect.center().y())
                    self._hover_h = float(rect.height())
                    vp_w = float(self.parent().width()) if self.parent() else float(self.width())
                    rect_w = float(rect.width()) if rect.width() > 20 else vp_w
                    self._hover_w = float(max(20, rect_w - 8))
                    self._hover_x = float(rect.x() + 4) if rect.width() > 20 else 4.0
                else:
                    self._hover_target_y = -100.0
        elif event.type() == QEvent.Leave:
            self._hover_target_y = -100.0
        elif event.type() in (QEvent.Resize, QEvent.Show):
            if not getattr(self, "_in_sync", False):
                self._sync_geometry()
        return False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if isinstance(self.target, QTabBar):
            # QTabBar horizontal
            if self._hover_alpha > 1 and self._hover_y >= 0:
                h_rect = QRectF(self._hover_y - self._hover_h / 2.0, 4, self._hover_h, self.height() - 8)
                painter.setBrush(QColor(255, 255, 255, int(self._hover_alpha)))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(h_rect, 8, 8)

            if self._blob_y >= 0:
                blob_rect = QRectF(self._blob_y - self._blob_h / 2.0, 4, self._blob_h, self.height() - 8)
                grad = QLinearGradient(blob_rect.topLeft(), blob_rect.bottomRight())
                grad.setColorAt(0.0, QColor(99, 102, 241, 140))
                grad.setColorAt(1.0, QColor(56, 189, 248, 100))
                painter.setBrush(grad)
                painter.setPen(QPen(QColor(165, 180, 252, 120), 1.0))
                painter.drawRoundedRect(blob_rect, 8, 8)
        else:
            # QListWidget / QListView vertical
            # 1. Hover pill
            if self._hover_alpha > 1 and self._hover_y >= 0:
                h_w = getattr(self, "_hover_w", self._blob_w)
                h_x = getattr(self, "_hover_x", self._blob_x)
                h_rect = QRectF(h_x, self._hover_y - self._hover_h / 2.0 + 1, h_w, self._hover_h - 2)
                painter.setBrush(QColor(255, 255, 255, int(self._hover_alpha)))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(h_rect, 8, 8)

            # 2. Active Liquid Selection Blob
            if self._blob_y >= 0:
                blob_rect = QRectF(self._blob_x, self._blob_y - self._blob_h / 2.0 + 1, self._blob_w, self._blob_h - 2)
                grad = QLinearGradient(blob_rect.topLeft(), blob_rect.bottomRight())
                grad.setColorAt(0.0, QColor(99, 102, 241, 80))
                grad.setColorAt(1.0, QColor(56, 189, 248, 50))
                painter.setBrush(grad)
                painter.setPen(QPen(QColor(165, 180, 252, 100), 1.0))
                painter.drawRoundedRect(blob_rect, 8, 8)


def apply_liquid_overlay(target):
    """Gắn LiquidOverlayWidget cho một QListWidget hoặc QTabBar nếu chưa có."""
    if target is None:
        return None
    if not getattr(target, "_has_liquid_overlay", False):
        overlay = LiquidOverlayWidget(target)
        target._has_liquid_overlay = True
        target._liquid_overlay = overlay
        return overlay
    return getattr(target, "_liquid_overlay", None)
