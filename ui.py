# UI/screen/debugger for CPU emulator
# v1.1

from assembler import assemble
from disassembler import disassemble
import tkinter as tk
import time
from PIL import Image, ImageTk

class EmulatorUI:
    def __init__(self, root, cpu, memory, timer):
        self.root = root
        self.cpu = cpu
        self.memory = memory
        self.mem = memory.mem
        self.timer = timer     # Timer externo para generar interrupcipnes
        self.use_nmi = False   # Con False, el timer se "conecta" las señal de IRQ, con True a NMI
        self.frame_ready = False # Es para actualizar framebuffer con los tick del timer.
        self.latched_buffer = bytearray(0x6000)  # 24 Kb, es para capturar la memoria y actualizar el fb

        # Simulación del reloj de CPU basada en ciclos por instrucción (frecuencia objetivo aproximada: 1.2 MHz)
        self.cpu_hz = 2000000   # 2.0 MHz!
        self.seconds_per_cycle = 1.0 / self.cpu_hz
        self.cycles_per_batch = 20000 # This is at full speed, at less speed -> less cycles per batch
        
        # For speed testing purposes
        #self.loops = 0  
        
        self.root.bind("<KeyPress>", self.on_key_press) # Escuchar teclado
        self.root.bind("<KeyRelease>", self.on_key_release)

        self.tecla_activa_char = None
        self.tecla_activa_keysym = None
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

        # Control de velocidad
        self.speed_frame = tk.Frame(self.left_frame)
        self.speed_frame.pack(side=tk.TOP, fill=tk.X, pady=4)

        tk.Label(self.speed_frame, text="Speed:").pack(side=tk.LEFT, padx=(5, 10))
        self.speed = tk.DoubleVar(value=1.0)  # 1 es 100%

        tk.Radiobutton(self.speed_frame, text="0.1%", variable=self.speed, value=0.001).pack(side=tk.LEFT)
        tk.Radiobutton(self.speed_frame, text="1%", variable=self.speed, value=0.01).pack(side=tk.LEFT)
        tk.Radiobutton(self.speed_frame, text="10%", variable=self.speed, value=0.1).pack(side=tk.LEFT)
        tk.Radiobutton(self.speed_frame, text="100%", variable=self.speed, value=1.0).pack(side=tk.LEFT)

        # Botones de control
        self.btn_frame = tk.Frame(self.left_frame)
        self.btn_frame.pack(side=tk.TOP, fill=tk.X)
        tk.Button(self.btn_frame, text="Asm/Load", command=self.load_program).pack(side=tk.LEFT)
        tk.Button(self.btn_frame, text="Run/Pause", command=self.run).pack(side=tk.LEFT)
        tk.Button(self.btn_frame, text="Step", command=self.step).pack(side=tk.LEFT)
        tk.Button(self.btn_frame, text="Reset", command=self.reset).pack(side=tk.LEFT)

        ### Frame derecho principal
        self.right_frame = tk.Frame(root)
        self.right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ## TOP: FRAMEBUFFER con Pillow
        self.canvas = tk.Canvas(
            self.right_frame,
            width=256 * self.scale,
            height=192 * self.scale,
            bg="black"
        )
        self.canvas.pack(side=tk.TOP)

        self.img_pil = Image.new("RGB", (256, 192))
        self.img_tk = ImageTk.PhotoImage(
            self.img_pil.resize((256 * self.scale, 192 * self.scale), Image.NEAREST)
        )
        self.canvas.create_image((0, 0), image=self.img_tk, anchor="nw")

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

        # Color list
        self.palette = [
            (0,0,0), (0,0,128), (0,128,0), (0,128,128),
            (128,0,0), (128,0,128), (128,128,0), (192,192,192),
            (128,128,128), (0,0,255), (0,255,0), (0,255,255),
            (255,0,0), (255,0,255), (255,255,0), (255,255,255)
        ]

        # Precalculated color table: creates 6 bytes RGB for every posible byte value (1 byte = 2 pixels)
        self.lookup_rgb = [
            bytes(self.palette[(b >> 4) & 0x0F] + self.palette[b & 0x0F]) 
            for b in range(256)
        ]

        # Conectar scrollbar al Text
        mem_scroll.config(command=self.mem_view.yview)
        # Construye memoria una vez armado el wigget para verla
        self.build_memory_view()

        # Actualiza en init para que se vean los registros desde el comienzo
        self.reg_label.config(text= " " + "\n" + " ") # Deja el espacio en blanco, el visor aparece con Run o Step
        self.update_views()
        self.screen_loop()  # inicia el loop de refresh de la pantalla



    # Boton Step
    def step(self):
        self.system_step()
        self.update_views()

    def system_step(self):
        c = self.cpu.step()
        self.timer.update() # actualizar timer (tiempo real)
        mem = self.mem

        if self.timer.state:    # si hay una señal pendiente del timer
            self.timer.state = False
            self.latched_buffer = bytearray(mem[0x6000:0xC000]) # Native copy in one memory acces
            self.frame_ready = True  # señal para render

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
        speed = self.speed.get()
        cycles_per_batch = self.cycles_per_batch * speed
        seconds_per_cycle = self.seconds_per_cycle / speed
        system_step = self.system_step
        root_after = self.root.after
        running = self.cpu.running
        hz = self.cpu_hz * speed
        
        if not running:         # Si la CPU está detenida (HLT o en pausa), no ejecuta
            self.update_views()
            return

        start_time = time.perf_counter()  # tiempo real al inicio
        cycles = 0  # ciclos ejecutados en este batch

        # Ejecutar CPU hasta alcanzar cierta cantidad de ciclos
        while cycles < cycles_per_batch:
            c = system_step()   # ejecuta 1 instrucción
            cycles += c         # acumula ciclos

        elapsed = time.perf_counter() - start_time     # tiempo real transcurrido, incluye update de framebuffer
        expected = cycles * seconds_per_cycle          # tiempo que debería haber tomado

        # Micropausa si va a más de los MHz deseados
        if expected > (elapsed+0.01): time.sleep(expected - elapsed)  # Agregado de 10 ms reduce la cant de micropausas y el render mejora

        # Estimaciones de velocidad, solo para test
        #self.loops +=1
        #if self.loops == hz//cycles_per_batch*10: print(hz/1000000) # Imprime los MHz, deberia tardar ~10 seg.

        # reprogramar próximo ciclo sin bloquear UI (da lugar para pescar interrupcones y botones)
        self.loop_id = root_after(1, self.run_loop) # 1ms, cuanto menos mejor para mejorar los MHz

    def screen_loop(self):
        mem = self.mem
        char = self.tecla_activa_char
        if self.frame_ready:
            # This is to inject keys pressed into memory (independent from OS key autorepeat)
            if char is not None:
                char_code = ord(char) if len(char) == 1 else 0             
                if char_code > 0:
                    mem[0xC001] = char_code & 0xFF
                    mem[0xC000] = 0x80            
            
            self.frame_ready = False
            self.update_screen()
        self.root.after(1, self.screen_loop)

    def update_views(self):
        mem = self.mem
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
        self.update_memory()      
        # SCREEN
        self.latched_buffer = bytearray(mem[0x6000:0xC000])
        self.update_screen()

    # Reset button
    def reset(self):
        mem = self.mem
        # Cancelar el after del loop 
        if self.loop_id: self.root.after_cancel(self.loop_id)
        # limpiar memoria
        mem[:] = b'\x00' * 65536
        # reiniciar CPU
        self.cpu.reset()
        # resetear "shadow buffer" de pantalla
        self.prev_screen = [0] * (128 * 192)
        # reconstruir visor de memoria
        self.build_memory_view()
        # marcar que no hay programa cargado y que frenar el CPU
        self.program_loaded = False

        # actualizar UI
        self.update_views()
        
        #self.loops = 0  # For speed testing purposes

    # Memory viewer, se ejecuta 1 sola vez al cargar el programa
    def build_memory_view(self):
        mem = self.mem
        self.mem_view.delete("1.0", tk.END)
        
        for i in range(0x0000, 0x10000, 16):
            line = f"{i:04X}: "
            for j in range(16):
                val = mem[i + j]
                line += f"{val:02X} "
            self.mem_view.insert(tk.END, line + "\n")
            
    def update_memory(self):
        mem = self.mem
        # guardar posición real del scroll
        top_index = self.mem_view.index("@0,0")
        for i in range(0x0000, 0x10000, 16):
            line_index = i // 16 + 1
            line = f"{i:04X}: "
            for j in range(16):
                val = mem[i + j]
                line += f"{val:02X} "
            self.mem_view.replace(f"{line_index}.0", f"{line_index}.end", line)

        # restaurar scroll real
        self.mem_view.see(top_index)

    # Pantalla, aca es donde la emulacion puede perder performance con tkinter
    def update_screen(self):
        buf = self.latched_buffer   # The latched buffer prevents glitches from reading changing RAM

        # Traslates all the buffer instantly using the pre-calcualted table
        # This method uses an optimized implicit loop in C
        rgb_bytes = b"".join(self.lookup_rgb[b] for b in buf)  # Pastes bytes toghether, with no separation ("")

        # Creates RGB image directly
        self.img_pil = Image.frombytes("RGB", (256, 192), rgb_bytes)
        
        if self.scale == 1:
            self.img_tk.paste(self.img_pil)
        else:
            self.img_tk.paste(
                self.img_pil.resize((256 * self.scale, 192 * self.scale), Image.NEAREST)
            )

    def on_key_press(self, event):

        self.tecla_activa_char = event.char
        self.tecla_activa_keysym = event.keysym.lower()
        
        #mem = self.mem
        #self.keys_pressed[event.keysym.lower()] = True
        
        # Obtiene el código ASCII de la tecla
        #char_code = ord(event.char) if len(event.char) == 1 else 0
        
        #if char_code > 0:
        #    # Escribe el ASCII en RAM 0xC001
        #    mem[0xC001] = char_code & 0xFF
            
            #Pone el bit 7 en 1 ($80) en el registro de STATUS de 0xC000
        #    mem[0xC000] = 0x80
            
            # Activar si se quiere enviar interrupción, sino de usa por polling en el código ASM
            # self.cpu.request_irq()

    def on_key_release(self, event):
        if event.keysym.lower() == self.tecla_activa_keysym:
            self.tecla_activa_char = None
            self.tecla_activa_keysym = None
        
    # Cargar el programa
    def load_program(self):
        mem = self.mem
        # reset
        mem[:] = b'\x00' * 65536
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
        self.update_views()
        
        # Muestra los segmentos programa en consola, solo para debug
        for j in range(0,len(segments)):
            for i in range(0,len(segments[j][1])):
                if i % 16 == 0:
                    print(f"\n{segments[j][0]+i:04X}:", end=" ")
                print(f"{mem[segments[j][0]+i]:02X}", end=" ", flush=True)
            print(f"   {len(segments[j][1])} bytes")
                # El flush manda el texto inmediatamente a la salida, sin esperar que se llene el buffer

