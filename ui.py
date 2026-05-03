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
        self.timer = timer     # Timer externo para generar interrupcipnes

        # Reloj que hace correr el CPU a 1MHz
        self.cpu_hz = 1000000
        self.seconds_per_cycle = 1.0 / self.cpu_hz
        self.cycles_per_batch = 2000

        self.program_loaded = False
        self.scale = 3  # para la pantalla: 3 pixeles por "pixel"
        self.prev_screen = [0] * (256 * 160)  # guarda el estado anterior de cada "pixel"

        ### Frame izquierdo (editor + botones)
        self.left_frame = tk.Frame(root)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True) #el Text se estira verticalmente para llenar el frame.

        # Editor ASM arriba
        self.editor = tk.Text(self.left_frame, height=30, width=60)
        self.editor.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Botones
        self.btn_frame = tk.Frame(self.left_frame)
        self.btn_frame.pack(side=tk.TOP, fill=tk.X)
        tk.Button(self.btn_frame, text="Run", command=self.run).pack(side=tk.LEFT)
        tk.Button(self.btn_frame, text="Step", command=self.step).pack(side=tk.LEFT)
        tk.Button(self.btn_frame, text="Reset", command=self.reset).pack(side=tk.LEFT)

        ### Frame derecho principal
        self.right_frame = tk.Frame(root)
        self.right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # TOP: FRAMEBUFFER
        self.canvas = tk.Canvas(
            self.right_frame,
            width=256 * self.scale,
            height=160 * self.scale,
            bg="black"
        )
        self.canvas.pack(side=tk.TOP)

        # BOTTOM: CONTENEDOR HORIZONTAL
        self.bottom_frame = tk.Frame(self.right_frame)
        self.bottom_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # IZQUIERDA: REGISTROS
        self.reg_frame = tk.Frame(self.bottom_frame, width=300)
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

        self.mem_header = tk.Text(self.mem_frame, height=1, width=60)
        self.mem_header.pack(fill=tk.X)

        header = "      " + " ".join(f"{i:02X}" for i in range(16))
        self.mem_header.insert("1.0", header)
        self.mem_header.config(state="disabled")

        mem_scroll = tk.Scrollbar(self.mem_frame)
        mem_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.mem_view = tk.Text(
            self.mem_frame,
            height=16,
            width=60,
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
            self.cpu.request_irq()   # En este caso, el timer esta "cableado" al IRQ.
            # Generar flanco de NMI. Comentando la linea anterior y activando las 2 siguientes, el timer envia NMIs.
            # self.cpu.set_nmi_line(True)  # NMI dispara en la transición de FALSE a TRUE (flanco ascendente)
            # self.cpu.set_nmi_line(False) # Se pone en FALSE para "armar" le proximo flanco, si viene de un TRUE anterior no se dispara.
        return c

    # Boton Run
    def run(self):
        if not self.program_loaded:
            self.load_program()

        self.cpu.running = True
        self.run_loop()

    def run_loop(self):
        if not self.cpu.running:         # Si la CPU está detenida (HLT), no ejecuta
            self.update_views()
            return

        start_time = time.perf_counter()  # tiempo real al inicio
        cycles = 0  # ciclos ejecutados en este batch

        # Ejecutar CPU hasta alcanzar cierta cantidad de ciclos
        while cycles < self.cycles_per_batch:
            c = self.system_step()   # ejecuta 1 instrucción
            cycles += c                  # acumula ciclos


        elapsed = time.perf_counter() - start_time          # tiempo real transcurrido
        expected = cycles * self.seconds_per_cycle          # tiempo que debería haber tomado

        if expected > elapsed:
            time.sleep(expected - elapsed)  # frenar si vamos demasiado rápido

        self.update_views()  # refrescar UI
        self.root.after(1, self.run_loop)  # reprogramar próximo ciclo no bloquea UI, da lugar para pescar interrupcones)

    # Boton Step
    def step(self):
        if not self.program_loaded:
            self.load_program()
        else:
            if self.cpu.running:
                self.system_step()
        self.update_views()

    def update_views(self):
        flags = f"[{'Z' if self.cpu.Z else '-'}{'N' if self.cpu.N else '-'}{'C' if self.cpu.CF else '-'}{'V' if self.cpu.V else '-'}{'I' if self.cpu.I else '-'}]"

        part1 = (
            f"\n  Program Counter: 0x{self.cpu.PC:04X}\n"
            f"  Stack Pointer:   0x{self.cpu.SP:04X}\n\n"
            f"  Registers:\n"
            f"  A: 0x{self.cpu.A:02X}   0b{self.cpu.A:08b}\n"
            f"  B: 0x{self.cpu.B:02X}   0b{self.cpu.B:08b}\n"
            f"  C: 0x{self.cpu.C:02X}   0b{self.cpu.C:08b}\n"
            f"  D: 0x{self.cpu.D:02X}   0b{self.cpu.D:08b}\n\n"
            f"  FLAGS: {flags}\n\n"
            f"  Next instruction:"
        )

        part2 = disassemble(self.cpu)
        self.reg_label.config(text=part1 + "\n  0x" + part2)
        # MEMORY VIEW
        self.update_memory_line(self.cpu.PC)
            
        if self.memory.last_write is not None:
            self.update_memory_line(self.memory.last_write)
            self.memory.last_write = None
        # SCREEN
        self.update_screen()

# Boton Reset
    def reset(self):
        # limpiar memoria
        self.memory.mem = [0] * 0x10000
        # reiniciar CPU
        self.cpu.reset()
        # resetear buffer de pantalla
        self.prev_screen = [0] * (256 * 160)
        # limpiar canvas
        self.canvas.delete("all")
        # reconstruir visor de memoria
        self.build_memory_view()
        # marcar que no hay programa cargado y que frenar el CPU
        self.program_loaded = False
        self.cpu.running = False
        # actualizar UI
        self.update_views()

# Memory viewer, se ejecuta 1 sola vez al cargar el programa, despues update_view actualiza linas puntuales de memoria
    def build_memory_view(self):
        self.mem_view.delete("1.0", tk.END)

        for i in range(0x0000, 0x10000, 16):
            line = f"{i:04X}: "
            for j in range(16):
                val = self.memory.read(i + j)
                line += f"{val:02X} "
            self.mem_view.insert(tk.END, line + "\n")
            
    def update_memory_line(self, addr):
        base = addr & 0xFFF0
        line_index = base // 16 + 1

        # guardar posición real del scroll
        top_index = self.mem_view.index("@0,0")

        line = f"{base:04X}: "
        for j in range(16):
            val = self.memory.read(base + j)
            line += f"{val:02X} "

        self.mem_view.replace(f"{line_index}.0", f"{line_index}.end", line)

        # restaurar scroll real
        self.mem_view.see(top_index)

# Pantalla
    def update_screen(self):
        #self.canvas.delete("all")
        base = 0x6000

        for y in range(160):
            for x in range(256):
                addr = base + y * 256 + x
                val = self.memory.read(addr)
                
                idx = y * 256 + x

                # solo si cambió. Esto es mas rapido que dibujar toda la pantalla de vuelta
                if val != self.prev_screen[idx]:
                    self.prev_screen[idx] = val
                
                    # elegir color
                    if val == 0:
                        color = "black"
                    else:
                        # color = f"#{val:02X}{val:02X}{val:02X}"  # version original en escala de grises
                        # Color RGB a partir de un numero de 8 bits:
                        color = bits8_a_rgb(val)

                    # dibujar pixel (con escala)
                    self.canvas.create_rectangle(
                        x * self.scale,
                        y * self.scale,
                        (x + 1) * self.scale,
                        (y + 1) * self.scale,
                        fill=color,
                        outline=color
                    )

# Nota sobre color: tkinter usa #RRGGBB. Lo que hace la linea "color = ..."
# Es asignar el valor del mismo byte de la memoria 3 veces, uno para cada color
# Eso genera basicamente una escala de grises de #000000 a #FFFFFF (blanco)
# si se quiere uan escala de color puntal se puede editar eso.


# Cargar el programa
    def load_program(self):

        # reset
        self.memory.mem = [0] * 0x10000
        self.cpu.__init__(self.memory)

        #Ensamblar codigo
        code = self.editor.get("1.0", tk.END)
        segments = assemble(code)

        # cargar programa en memoria (direccion x0100)
        for addr, data in segments:
            for i, byte in enumerate(data):
                self.memory.write(addr + i, byte)

        self.cpu.running = True
        self.program_loaded = True
        
        self.build_memory_view()
        self.memory.last_write = None
        
        # Muestra long de programa en bytes y memoria en consola, solo para debug, se puede desactivar.
        #print(f"\n{len(program)}")
        #for i in range(0x100,len(program)+0x100):
        #    if i % 16 == 0:
        #            print(f"\n{i:04X}:", end=" ")
        #    print(f"{self.memory.read(i):02X}", end=" ", flush=True)
            # El flush manda el texto inmediatamentew a la salida, sin esperar que se llene el buffer
 
# Funcion para convertir 8 bits al formato RGB
def bits8_a_rgb(valor):
    r3 = (valor >> 5) & 0b11
    g3 = (valor >> 2) & 0b111
    b2 = valor & 0b111

    # Escalar de vuelta a 0–255
    r = int(r3 * 255 / 3)
    g = int(g3 * 255 / 7)
    b = int(b2 * 255 / 7)
    return f"#{r:02X}{g:02X}{b:02X}"  # Formatea r, g y b para que queden los hex #RRGGBB


