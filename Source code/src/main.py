import sys

import config  # noqa: F401  (tạo thư mục dữ liệu và đặt MPLCONFIGDIR trước khi nạp matplotlib)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from ui import MainWindow, apply_theme


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Agenty")
    app.setFont(QFont("Segoe UI", 11))
    cfg = config.load_config()
    apply_theme(app, cfg.get("theme", "dark"), cfg.get("font_size", "medium"))
    app.main_window = MainWindow()  # giữ tham chiếu; Cài đặt có thể thay bằng cửa sổ mới
    app.main_window.show()
    code = app.exec()
    from ui import wait_background
    wait_background()  # đợi luồng nền (tải danh sách model...) kết thúc trước khi thoát
    sys.exit(code)


if __name__ == "__main__":
    main()
