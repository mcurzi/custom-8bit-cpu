# De acá se ejecuta el emulador con la UI.
# Requiere cpu.py, assembler.py y disassembler.py

from cpu import CPU
from memory import Memory 
from ui import EmulatorUI     # ui.py, esta a su vez carga assembler.py y disassembler.py
from timer import Timer  # o donde tengas definida la clase
import tkinter as tk

mem = Memory()
cpu = CPU(mem)

# This timer generates an interruption signal. It can be disabled with freq_hz=0
timer = Timer(freq_hz=60)

root = tk.Tk()
# Creates user interface and connects everything
ui = EmulatorUI(root, cpu, mem, timer)

def safe_exit():
    ui.reset() 
    root.destroy()

root.protocol("WM_DELETE_WINDOW", safe_exit)

# Set UI window title
root.title("Custom 8-bit Architecture Emulator [v1.0]")

# Run UI loop
root.mainloop()
