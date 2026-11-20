"""Punto de entrada para `python3 -m parking`.

`--headless` dirige la ejecución al modo sin GUI. Sin esta opción se lanza la GUI de Tk.
La GUI se importa de forma diferida para que el modo sin GUI nunca use tkinter.
"""
import sys


def _launch_gui():
    from parking.gui import app  # diferido: tkinter solo se necesita en la ruta de la GUI
    return app.main()


def _main(argv):
    if "--headless" in argv:
        from parking.headless import main as headless_main
        return headless_main(argv)
    return _launch_gui()


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
