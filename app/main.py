# app/main.py

from __future__ import annotations

from app.ui_tk.main_window_tk import MainWindowTk


def main():
    app = MainWindowTk()
    app.mainloop()


if __name__ == "__main__":
    main()
