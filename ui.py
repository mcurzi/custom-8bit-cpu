# User interface basica para el emulador de CPU
# v1

#from cpu import CPU, Memory   
from assembler import assemble
from disassembler import disassemble
import tkinter as tk
import time


class EmulatorUI:
    def __init__(self, root, cpu, memory, timer):
        self.root = root
        self.cpu = cpu
        self.memory = memory
        self.mem = memory.mem
        self.last_write = None
        self.timer = timer     # Timer externo para generar interrupcipnes
        self.use_nmi = False   # Con False, el timer se "conecta" las señal de IRQ, con True a NMI

        # Simulación del reloj de CPU basada en ciclos por instrucción (frecuencia objetivo aproximada: 1.2 MHz)
        self.cpu_hz = 1200000
        self.seconds_per_cycle = 1.0 / self.cpu_hz
        self.cycles_per_batch = 20000  # hace batches de esta cantidad de ciclos, luego chequea el tiempo transcurrido y ajusta velocidad
        # self.loops = 0  # For speed testing purposes
        
        self.root.bind("<Key>", self.on_key_press) # Escuchar teclado

        self.program_loaded = False
        self.loop_id = None

        # Variables del framebuffer
        self.scale = 2  # Aumenta la escala (pixeles por "pixel")
        self.prev_screen = [0] * (128 * 192)  # guarda el estado anterior de cada byte (2 pixeles). Esto evita redibujar toda la pantalla.

        ### Frame izquierdo (editor + botones)
        self.left_frame = tk.Frame(root)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True) # el Text se estira verticalmente para llenar el frame.

        # Editor ASM arriba
        self.editor = tk.Text(self.left_frame, height=40, width=80)
        self.editor.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Botones
        self.btn_frame = tk.Frame(self.left_frame)
        self.btn_frame.pack(side=tk.TOP, fill=tk.X)
        tk.Button(self.btn_frame, text="Asm/Load", command=self.load_program).pack(side=tk.LEFT)
        tk.Button(self.btn_frame, text="Run/Pause", command=self.run).pack(side=tk.LEFT)
        tk.Button(self.btn_frame, text="Step", command=self.step).pack(side=tk.LEFT)
        tk.Button(self.btn_frame, text="Reset", command=self.reset).pack(side=tk.LEFT)

        ### Frame derecho principal
        self.right_frame = tk.Frame(root)
        self.right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # TOP: FRAMEBUFFER
        self.canvas = tk.Canvas(
            self.right_frame,
            width=256 * self.scale,
            height=192 * self.scale,
            bg="black"
        )
        self.canvas.pack(side=tk.TOP)

        # Este bloque crea la grilla de pixeles una sola vez. Después solo cambiaa colores
        self.screen_rects = []  # Matriz 2D con el id interno de cada rectangulo ("pixel")
        for y in range(192):
            row = []
            for x in range(256):
                rect = self.canvas.create_rectangle(
                    x * self.scale, y * self.scale,
                    (x + 1) * self.scale, (y + 1) * self.scale,
                    fill="black",
                    outline=""  # Aparentemente sin outine es mas rapido porque no lo tiene que actualizar en cada frame
                )
                row.append(rect)
            self.screen_rects.append(row)


        # BOTTOM: CONTENEDOR HORIZONTAL
        self.bottom_frame = tk.Frame(self.right_frame)
        self.bottom_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # IZQUIERDA: REGISTROS
        self.reg_frame = tk.Frame(self.bottom_frame, width=200)
        self.reg_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.reg_frame.pack_propagate(False)

        self.reg_label = tk.Label(
            self.reg_frame,
            text="",
            font=("Courier", 10),
            justify="left",
            anchor="nw"
        )
        self.reg_label.pack(anchor="nw")

        self.instr_label = tk.Label(
            self.reg_frame,
            text="",
            font=("Courier", 10),
            justify="left",
            anchor="nw"
        )
        self.instr_label.pack(anchor="nw")

        # DERECHA: MEMORIA
        self.mem_frame = tk.Frame(self.bottom_frame)
        self.mem_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.mem_header = tk.Text(self.mem_frame, height=1, width=55)
        self.mem_header.pack(fill=tk.X)

        header = "      " + " ".join(f"{i:02X}" for i in range(16))
        self.mem_header.insert("1.0", header)
        self.mem_header.config(state="disabled")

        mem_scroll = tk.Scrollbar(self.mem_frame)
        mem_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.mem_view = tk.Text(
            self.mem_frame,
            height=16,
            width=55,
            yscrollcommand=mem_scroll.set,
            font=("Courier", 10)
        )
        self.mem_view.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Conectar scrollbar al Text
        mem_scroll.config(command=self.mem_view.yview)
        # Construye memoria una vez armado el wigget para verla
        self.build_memory_view()

        # Actualiza en init para que se vean los registros desde el comienzo
        self.reg_label.config(text= " " + "\n" + " ") # Deja el espacio en blanco, el visor aparece con Run o Step
        self.update_views()

    def system_step(self):
        c = self.cpu.step()
        self.timer.update() # actualizar timer (tiempo real)

        if self.timer.state:    # si hay una señal pendiente del timer
            self.timer.state = False

            if self.use_nmi:
                self.cpu.set_nmi_line(True)  # NMI dispara en la transición de FALSE a TRUE (flanco ascendente)
                self.cpu.set_nmi_line(False)  # Se pone en FALSE para "armar" le proximo flanco, si viene de un TRUE anterior no se dispara.
            else:
                self.cpu.request_irq()
        return c

    # Boton Run
    def run(self):
        if self.program_loaded and not self.cpu.running:
            self.cpu.running = True
            self.run_loop()
        elif self.cpu.running:
            self.cpu.running = False

    def run_loop(self):
        cycles_per_batch = self.cycles_per_batch
        seconds_per_cycle = self.seconds_per_cycle
        running = self.cpu.running
        if not running:         # Si la CPU está detenida (HLT), no ejecuta
            self.update_views()
            return

        start_time = time.perf_counter()  # tiempo real al inicio
        cycles = 0  # ciclos ejecutados en este batch

        # Ejecutar CPU hasta alcanzar cierta cantidad de ciclos
        while cycles < cycles_per_batch:
            c = self.system_step()   # ejecuta 1 instrucción
            cycles += c                  # acumula ciclos

        #self.update_views()  # refrescar UI
        self.update_screen()  # Refresca solo framebuffer, ni memoria, ni registros ni desensamblado

        elapsed = time.perf_counter() - start_time     # tiempo real transcurrido, incluye update de framebuffer
        expected = cycles * seconds_per_cycle          # tiempo que debería haber tomado

        # Micropausa si va a más de los MHz deseados
        if expected > (elapsed + 8): time.sleep(expected - elapsed) # 8ms es la pausa del root.afer()

        # Calculo de velocidad, solo para test
        # self.loops +=1
        # if self.loops == 600: print(self.loops*cycles_per_batch) # Imprime 12.000.000, deberia tardar ~10 segundos.

        # reprogramar próximo ciclo sin bloquear UI (da lugar para pescar interrupcones y botones)
        self.loop_id = self.root.after(8, self.run_loop) # 8ms, es 125 veces por segundo


    # Boton Step
    def step(self):
        self.system_step()
        self.update_views()

    def update_views(self):
        flags = f"[{'Z' if self.cpu.Z else '-'}{'N' if self.cpu.N else '-'}{'C' if self.cpu.CF else '-'}{'V' if self.cpu.V else '-'}{'I' if self.cpu.I else '-'}]"

        part1 = (
            f"\n  PC: 0x{self.cpu.PC:04X}\n  SP: 0x{self.cpu.SP:04X}\n"
            f"  FLAGS: {flags}\n\n"
            f"  Registers:\n"
            f"  A: 0x{self.cpu.A:02X}   0b{self.cpu.A:08b}\n"
            f"  B: 0x{self.cpu.B:02X}   0b{self.cpu.B:08b}\n"
            f"  C: 0x{self.cpu.C:02X}   0b{self.cpu.C:08b}\n"
            f"  D: 0x{self.cpu.D:02X}   0b{self.cpu.D:08b}\n\n"
            f"  Next instruction:"
        )

        part2 = disassemble(self.cpu)
        self.reg_label.config(text=part1 + "\n  " + part2)
        # MEMORY VIEW
        self.update_memory_line(self.cpu.PC)
              
        if self.last_write is not None:
            self.update_memory_line(self.last_write)
            self.last_write = None
        if self.cpu.last_write is not None:
            self.update_memory_line(self.cpu.last_write)
            self.cpu.last_write = None            
        # SCREEN
        self.update_screen()

# Boton Reset
    def reset(self):
        # Cancelar el after del loop 
        if self.loop_id: self.root.after_cancel(self.loop_id)
        # limpiar memoria
        self.memory.mem[:] = b'\x00' * 65536
        # reiniciar CPU
        self.cpu.reset()
        # resetear "shadow buffer" de pantalla
        self.prev_screen = [0] * (128 * 192)
        # limpiar canvas, pero sin destruirlo
        for y in range(192):
            for x in range(256):
                self.canvas.itemconfig(
                    self.screen_rects[y][x],
                    fill="black",
                    outline=""
                )
        # reconstruir visor de memoria
        self.build_memory_view()
        # marcar que no hay programa cargado y que frenar el CPU
        self.program_loaded = False
        # self.loops = 0  # For speed testing purposes
        # actualizar UI
        self.update_views()

# Memory viewer, se ejecuta 1 sola vez al cargar el programa, despues update_view actualiza linas puntuales de memoria
    def build_memory_view(self):
        mem = self.mem
        self.mem_view.delete("1.0", tk.END)

        for i in range(0x0000, 0x10000, 16):
            line = f"{i:04X}: "
            for j in range(16):
                val = mem[i + j]
                line += f"{val:02X} "
            self.mem_view.insert(tk.END, line + "\n")
            
    def update_memory_line(self, addr):
        mem = self.mem
        base = addr & 0xFFF0
        line_index = base // 16 + 1

        # guardar posición real del scroll
        top_index = self.mem_view.index("@0,0")

        line = f"{base:04X}: "
        for j in range(16):
            val = mem[base + j]
            line += f"{val:02X} "

        self.mem_view.replace(f"{line_index}.0", f"{line_index}.end", line)

        # restaurar scroll real
        self.mem_view.see(top_index)

# Pantalla, aca es donde la emulacion puede perder performance con tkinter
    def update_screen(self):
        mem = self.mem
        base = 0x6000
        prev = self.prev_screen

        # Una lista es más rápida que un diccionario para índices numéricos
        PALETTE_16 = [
            "black", "navy", "green", "teal", "maroon", "purple", "olive", "silver",
            "gray", "blue", "lime", "cyan", "red", "magenta", "yellow", "white"
        ]

        # Referencias locales son mas rápidas en el loop
        itemconfig = self.canvas.itemconfig
        rects = self.screen_rects

        for y in range(192):
            y_offset = y * 128  # Precalculamos el offset de la fila
            rect_row = rects[y] # Referencia local a la fila de la matriz

            for x_byte in range(128):
                idx = y_offset + x_byte
                val = mem[base + idx]

                if val != prev[idx]:
                    prev[idx] = val

                    # Extraemos colores
                    c1 = PALETTE_16[(val >> 4) & 0x0F]
                    c2 = PALETTE_16[val & 0x0F]

                    # Actualizamos rectángulos (Solo relleno, sin tocar outline)
                    x_base = x_byte << 1 # x_byte * 2
                    itemconfig(rect_row[x_base], fill=c1)
                    itemconfig(rect_row[x_base + 1], fill=c2)

    def on_key_press(self, event):
        mem = self.mem
        # Obtiene el código ASCII de la tecla
        char_code = ord(event.char) if len(event.char) == 1 else 0
        
        if char_code > 0:
            # Escribe el ASCII en RAM 0xC001
            mem[0xC001] = char_code & 0xFF
            self.last_write = 0xC001
            
            #Pone el bit 7 en 1 ($80) en el registro de STATUS de 0xC000
            mem[0xC000] = 0x80
            self.last_write = 0xC000
            
            # Activar si se quiere enviar interrupción, sino de usa por polling en el código ASM
            # self.cpu.request_irq()


# Cargar el programa
    def load_program(self):
        mem = self.mem
        # reset
        self.memory.mem[:] = b'\x00' * 65536
        self.cpu.__init__(self.memory)

        #Ensamblar codigo
        code = self.editor.get("1.0", tk.END)
        segments = assemble(code)

        # cargar programa en memoria
        for addr, data in segments:
            for i, byte in enumerate(data):
                mem[addr + i] = byte

        self.program_loaded = True
        
        self.build_memory_view()
        self.last_write = None
        
        # Muestra los segmentos programa en consola, solo para debug
        for j in range(0,len(segments)):
            for i in range(0,len(segments[j][1])):
                if i % 16 == 0:
                    print(f"\n{segments[j][0]+i:04X}:", end=" ")
                print(f"{mem[segments[j][0]+i]:02X}", end=" ", flush=True)
            print(f"   {len(segments[j][1])} bytes")
                # El flush manda el texto inmediatamente a la salida, sin esperar que se llene el buffer

