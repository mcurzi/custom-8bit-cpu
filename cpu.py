### 8-bit CPU Emulator - custom ISA 
### v1.0

### Clase de Memoria
class Memory:
    def __init__(self):
        self.mem = [0] * 0x10000  # 64 KB
        self.last_write = None

    def read(self, addr):
        return self.mem[addr & 0xFFFF]

    def write(self, addr, value):
        # Normaliza inputs para el bus width del CPU
        addr = addr & 0xFFFF  # wrap-around 16-bit (direcciones 0x0000–0xFFFF)
        value = value & 0xFF  # wrap-around 8-bit (data bus 0x00–0xFF)
        self.mem[addr] = value
        self.last_write = addr  # Última dirección escrita


### CPU
class CPU:
    def __init__(self, memory: Memory): # Recibe instancia de Memory como input al ser creada
        self.memory = memory
        self.irq_pending = False
        self.nmi_pending = False
        self.nmi_line = False
        self.prev_nmi_line = False

        self.reset()  # reutiliza lógica, el reset apunta el PC directo al inicio del programa, no es un vector.

    def reset(self):
        # Registros
        self.A = 0
        self.B = 0
        self.C = 0
        self.D = 0

        self.SP = 0x6000 # Stack pointer. El stack usa memoria justo antes del framebuffer ($6000). Va hacia atras, por eso no la pisa.

        # Program counter inicia siempre en 0x100. El Z80 hace algo asi pero en 0x0000
        self.PC = 0x100   # Acá se debe cargar el programa. Queda $0000-$00FF libre para posible uso futuro

        # Leer vector de reset para ubicar el PC (6502 style)
        # addr = 0xFFFC
        # low = self.memory.read(addr)
        # high = self.memory.read(addr + 1)
        # self.pc = (high << 8) | low

        # Flags
        self.Z = 0
        self.N = 0
        self.CF = 0
        self.V = 0
        #self.B = 0  # Reservado para break flag
        self.I = 1  # IRQ deshabilitadas por defecto

        # control
        self.cc = 0
        self.cycles = 0
        # Running, es para el debugger de command line
        self.running = True

    ### DC helpers (16-bit)
    def get_dc(self):
        return (self.D << 8) | self.C

    def set_dc(self, value):
        value &= 0xFFFF
        self.C = value & 0xFF
        self.D = (value >> 8) & 0xFF

    ### Flags
    def update_zn(self, value):
        value &= 0xFF
        self.Z = int(value == 0)
        self.N = int((value & 0x80) != 0)

    def set_carry(self, cond):
        self.CF = int(cond)

    def set_overflow_add(self, a, b, r):  #Detecta overflow con signo: 127 + 1 = -128, entonces V = 1
        # En suma, V flag se activa cuando Pos + Pos = Neg (entre 0x80 y 0xFF) o 
        # cuando neg + neg = pos (entre 0 y 0x79). No se activa cuando se suman numeros de diferente signo
        r = r & 0xFF
        self.V = 1 if ((a ^ r) & (b ^ r) & 0x80) else 0  # V + 1 si tanto A como B tienen un signo distinto al de r
        
    def set_overflow_sub(self, a, b, r):
        # En Resta, V flag se activa cuando Pos - Neg = Neg o Neg - Pos = Pos
        # no hay overflow si los numeros que se restan tienen mismo signo
        # r es el resultado de (a - b - (1 - carry)) & 0xFF
        # Forzar que r solo tenga 8 bits, eso es porque Python maneja precision infinita y podria tener muchos unos hacia la izq.
        r = r & 0xFF
        # El overflow en resta ocurre si los signos de 'a' y 'b' son distintos
        # Y si el signo del resultado 'r' es distinto al de 'a'.
        self.V = int(((a ^ b) & (a ^ r) & 0x80) != 0)

    # Agrupar/desagrupar flags en 1 byte
    def pack_flags(self):
        byte = 0
        if self.N: byte |= (1 << 7)
        if self.V: byte |= (1 << 6)
        byte |= (1 << 5) # Bit 5, no se usa, se fija en 1
        # if self.B: byte |= (1 << 4) # Reservado para Break
        if self.I: byte |= (1 << 2)
        if self.Z: byte |= (1 << 1)
        if self.CF: byte |= (1 << 0)
        return byte

    def unpack_flags(self, byte):
        self.N = (byte & (1 << 7)) != 0
        self.V = (byte & (1 << 6)) != 0
        self.I = (byte & (1 << 2)) != 0
        self.Z = (byte & (1 << 1)) != 0
        self.CF = (byte & (1 << 0)) != 0

    ### Memory helpers
    def read16(self, addr):
        lo = self.memory.read(addr)
        hi = self.memory.read((addr + 1) & 0xFFFF)
        return lo | (hi << 8)

    # Calculo de indexados con page crossing.Esto no es indispensable para el 
    # funcionamiento del CPU, pero hace el calculo de ciclos más realista. Cuando
    # el indexado pasa a otra "pagina" de memoria, es decir, se incrementa el
    # high byte de la direccion (ej $01FF -> $0200) suma un ciclo adicional de CPU.
    def compute_indexed(self, base, index, base_cycles):
        lo = (base & 0xFF) + index
        carry = lo > 0xFF  # page crossing

        addr = ((base & 0xFF00) | (lo & 0xFF))

        cycles = base_cycles
        if carry:
            addr = (addr + 0x100) & 0xFFFF
            cycles += 1

        return addr, cycles

    ### Reg helpers (getting/setting)
    def get_reg(self, r):
        return getattr(self, r)

    def set_reg(self, r, v):
        return setattr(self, r, v & 0xFF) 
    
    #Stack helpers
    def push8(self, val):
        self.SP = (self.SP - 1) & 0xFFFF
        self.memory.write(self.SP, val & 0xFF)

    def pull8(self):
        val = self.memory.read(self.SP)
        self.SP = (self.SP + 1) & 0xFFFF
        return val
        
    def push16(self, val):
        # little endian
        self.push8((val >> 8) & 0xFF)  # high byte primero
        self.push8(val & 0xFF)         # Low byte en direccion mas baja de memoria

    def pull16(self):
        lo = self.pull8() # Pull del low byte primero.
        hi = self.pull8()  
        return lo | (hi << 8)
    
    #Interrupciones
    def handle_interrupt(self, vector_addr):
        # Push PC
        self.push16(self.PC)
        # Push flags
        self.push8(self.pack_flags())
        self.I = 1  # Bloquea IRQ mientras el handler trabaja
        # Saltar al vector
        self.PC = self.read16(vector_addr)

    def request_irq(self):
        self.irq_pending = True

    def set_nmi_line(self, state):
        # detectar flanco ascendente (latch de flanco como hardware real))
        if state and not self.prev_nmi_line:
            self.nmi_pending = True

        self.prev_nmi_line = state
        self.nmi_line = state

    # Adressing
    def resolve_address(self, bbb):
        mode = bbb

        if mode == 0:  # inmediato
            addr = self.PC
            self.PC += 1
            return addr, 1, 'imm'   # Devuelve direccion de memoria, ciclos, tipo

        if mode == 1:  # absoluto
            addr = self.read16(self.PC)
            self.PC += 2
            return addr, 2, 'mem'

        if mode == 2:  # abs + B
            base = self.read16(self.PC)
            self.PC += 2
            addr, cycles = self.compute_indexed(base, self.B, 3)
            return addr, cycles, 'mem'
            
        if mode == 3:  # abs + C
            base = self.read16(self.PC)
            self.PC += 2
            addr, cycles = self.compute_indexed(base, self.C, 3)
            return addr, cycles, 'mem'

        if mode == 4: # [DC]
            addr = self.get_dc()
            return addr, 2, 'mem'

        if mode == 5:
            ptr = self.read16(self.PC)
            self.PC += 2
            addr = self.read16(ptr)
            return addr, 4, 'mem'

        if mode == 6:  # [pointer] + B
            ptr = self.read16(self.PC)
            self.PC += 2
            base = self.read16(ptr)
            addr, cycles = self.compute_indexed(base, self.B, 5)
            return addr, cycles, 'mem'

        if mode == 7:  # [DC+B]
            base = self.get_dc()
            addr, cycles = self.compute_indexed(base, self.B, 3)
            return addr, cycles, 'mem'

        else:
            raise Exception("No se puede resolver la direccion")

    def fetch_operand(self, bbb):
        addr, cycles, kind = self.resolve_address(bbb)

        if kind == 'imm':
            return self.memory.read(addr), None, cycles
        else:
            return self.memory.read(addr), addr, cycles

    ### Metodo principal
    def step(self):

        # Primero chequeo de interrupciones
        if self.nmi_pending:        # Una NMI se ejecuta siempre, tiene prioridad
            self.nmi_pending = False
            self.handle_interrupt(0xFFFA)
            return 7  # ciclos aprox

        elif self.irq_pending and not self.I:  # Una IRQ solo se ejecuta cuando I flag es 0 y tiene menos prioridad que NMI.
            self.irq_pending = False
            self.handle_interrupt(0xFFFC)
            return 7

        # Fetch-Execute: Avanza una instrucción completa y actualiza los ciclos
        opcode = self.memory.read(self.PC)
        self.PC = (self.PC + 1) & 0xFFFF
        aaa = (opcode >> 5) & 0b111   # Right shift de 5 bits y un AND, el resultado es que se queda conlos 3 bits mas altos
        bbb = (opcode >> 2) & 0b111   # Se queda con un numero formado por bits 2, 3 y 4
        self.cc = opcode & 0b11   # Se queda con el numero formado por bits 0 y 1

        # Asignar ciclos según el tipo de instrucción
        cycles = 0

        if self.cc == 0b00:
            cycles = self.exec_alu(aaa, bbb)
        elif self.cc == 0b01:
            cycles = self.exec_mem(aaa, bbb)
        elif self.cc == 0b10:
            cycles = self.exec_flow(aaa, bbb)
        elif self.cc == 0b11:
            cycles = self.exec_special(aaa, bbb)
        else:
            raise Exception("Opcode no implementado")

        # Sumar los ciclos de la instrucción ejecutada
        self.cycles += cycles
        return cycles # Devuelve los ciclos usados por la instrucción ejecutada

    def advance_cycles(self, cycle_count):
        # Avanza múltiples ciclos a la vez
        cycles_left = cycle_count
        while cycles_left > 0:
            cycles_spent = self.step()  # Ejecuta una instrucción
            cycles_left -= cycles_spent  # Resta los ciclos usados
        return cycle_count - cycles_left  # Devuelve el número de ciclos avanzados

    ### ALU GROUP (CC=00)01 14 21 63 4
    def exec_alu(self, aaa, bbb):
        if aaa < 8:
            x, _, cycles = self.fetch_operand(bbb)

        if aaa == 0: # ADC, add with carry, asegurar CLC antes para sumar sin carry
            r = self.A + x + self.CF
            self.set_carry(r > 0xFF) # El carry se activa si el resultado total supera los 8 bits (255)
            r = r & 0xFF
            self.set_overflow_add(self.A, x, r) # no incluye valor de CF.
            self.set_reg('A', r)
            self.update_zn(r)
            cycles += 2

        elif aaa == 1:  # SBB, substract with borrow estilo Z80/8080 (no necesita SEC antes, asegurar CLC para restas sin borrow)
            new_carry = (x + self.CF) > self.A # El Carry se activa si todo lo que se resta (x + CF) es mayor que A (hubo préstamo)
            r = self.A - x - self.CF
            r = r & 0xFF #asegurar que el registro sea de 8 bits
            self.set_carry(new_carry)
            self.set_overflow_sub(self.A, x + self.CF, r) # Acá si el sustraendo incluye valor de CF.
            self.set_reg('A', r)
            self.update_zn(r)
            cycles += 2

        elif aaa == 2:  # AND
            r = self.A & x
            self.set_reg('A', r)
            self.update_zn(r)
            cycles += 1

        elif aaa == 3:  # ORA
            r = self.A| x
            self.set_reg('A', r)
            self.update_zn(r)
            cycles += 1

        elif aaa == 4:  # XOR
            r = self.A ^ x
            self.set_reg('A', r)
            self.update_zn(r)
            cycles += 1

        elif aaa == 5:  # CMP (Compara A)
            r = self.A - x
            r = r & 0xFF # Fuerza a 8 bits
            self.Z = int((r & 0xFF) == 0)
            self.N = int((r & 0x80) != 0)
            # self.CF = int(self.A >= x)   # CF estilo 6502
            self.CF = int(self.A < x)      # 1 si hay préstamo (A < x), estilo 8080/Z80
            self.set_overflow_sub(self.A, x, r) # CMP es resta pura, sin borrow implicito (el sustraendo es solo x, no x + CF)

        elif aaa == 6:  # CPB (Compara B)
            r = self.B - x
            r = r & 0xFF
            self.Z = int((r & 0xFF) == 0)
            self.N = int((r & 0x80) != 0)
            # self.CF = int(self.B >= x)
            self.CF = int(self.B < x)
            self.set_overflow_sub(self.B, x, r)

        elif aaa == 7:  # CPC (Compara C)
            r = self.C - x
            r = r & 0xFF
            self.Z = int((r & 0xFF) == 0)
            self.N = int((r & 0x80) != 0)
            # self.CF = int(self.C >= x)
            self.CF = int(self.C < x)
            self.set_overflow_sub(self.C, x, r)

        else:
            raise Exception(f"ALU opcode no implementado: aaa={aaa}, bbb={bbb}")


        return cycles

    ### MEMORY GROUP (CC=01)
    def exec_mem(self, aaa, bbb):
        if aaa < 4:  # LOAD
            v, addr, cycles = self.fetch_operand(bbb)
            cycles += 2
        elif aaa < 8:  # STORE
            if bbb == 0:
                raise Exception("STORE no soporta inmediato")
            else:
                addr, cycles, _ = self.resolve_address(bbb)
                cycles += 2
        
        if aaa == 0:  # LDA
            self.A = v
            self.update_zn(self.A)
        elif aaa == 1:  # LDB
            self.B = v
            self.update_zn(self.B)
        elif aaa == 2:  # LDC
            self.C = v
            self.update_zn(self.C)
        elif aaa == 3:  # LDD
            self.D = v
            self.update_zn(self.D)
        elif aaa == 4:  # STA
            self.memory.write(addr, self.A)
        elif aaa == 5:  # STB
            self.memory.write(addr, self.B)
        elif aaa == 6:  # STC
            self.memory.write(addr, self.C)
        elif aaa == 7:  # STD
            self.memory.write(addr, self.D)
        else:
            raise Exception(f"MEMORY opcode no implementado: aaa={aaa}, bbb={bbb}")

        return cycles

    ### FLOW GROUP (CC=10)
    def exec_flow(self, aaa, bbb):
        if bbb == 0:
            cond = True          # Branch/jump incondicional
        elif bbb == 1:
            cond = bool(self.Z)  # Branch/jmp  if equal (Z =1). No es obligatorio convertir a bool, pero ahorra warnings.
        elif bbb == 2:
            cond = not bool(self.Z)
        elif bbb == 3:
            cond = bool(self.N)      # Branch/jmp if carry set
        elif bbb == 4:
            cond = not bool(self.N)
        elif bbb == 5:
            cond = bool(self.CF)       # Branch/jmp  if minus
        elif bbb == 6:
            cond = not bool(self.CF)   # Branch/jmp  if not minus
        elif bbb == 7:
            cond = bool(self.V)       # Branch/jmp overflow

        # BRA / BSR, RELATIVOS (1 byte)
        if aaa == 2 or aaa == 3:
            offset = self.memory.read(self.PC)
            self.PC = (self.PC + 1) & 0xFFFF

            # convertir a signed (-128 a +127)
            if offset & 0x80:
                offset -= 0x100

            if not cond:
                return 2  # los returns devuelven nro de ciclos "inventado", en este caso es branch no tomado

            elif aaa == 2:  # BRA
                self.PC = (self.PC + offset) & 0xFFFF
                return 3  # tomado

            elif aaa == 3:  # BSR
                # push PC
                self.push16(self.PC)  # dirección de retorno, solo es correcto si PC ya apunta a la siguiente instrucción

                # salto relativo
                self.PC = (self.PC + offset) & 0xFFFF
                return 5 # tomado + stack

        # RESTO, ABSOLUTOS (2 bytes)
        elif 0 <= aaa <= 2:
            addr = self.read16(self.PC)
            self.PC = (self.PC + 2) & 0xFFFF

            if not cond:
                return 2 # condición falsa, jump no tomado

            elif aaa == 0:  # JMP
                self.PC = addr
                return 3

            elif aaa == 1:  # JSR
                self.push16(self.PC)
                # Salto absoluto
                self.PC = addr
                return 5

        elif aaa == 4:  # RET
            self.PC = self.pull16()
            return 5

        elif aaa == 5:  # RTI
            flags = self.pull8()
            self.unpack_flags(flags)
            self.PC = self.pull16()
            return 6

        else:
            raise Exception(f"FLOW no implementado: aaa={aaa}, bbb={bbb}")
        
        return 0

    ### SPECIAL GROUP (CC=11)
    def exec_special(self, aaa, bbb):
        cycles = 0
        reg_names = ["A", "B", "C", "D"]
        
        if aaa == 0:  # MOV
            cycles = 2
            if bbb == 0: # MOV A,B (origen, destino)
                self.B = self.A
                self.update_zn(self.B)
                return cycles
            elif bbb == 1:
                self.C = self.A
                self.update_zn(self.C)
                return cycles
            if bbb == 2:
                self.D = self.A
                self.update_zn(self.D)
                return cycles
            elif bbb == 3: # MOV B,A (origen, destino)
                self.A = self.B
                self.update_zn(self.A)
                return cycles
            elif bbb == 4:
                self.A = self.C
                self.update_zn(self.A)
                return cycles
            elif bbb == 5:
                self.A = self.D
                self.update_zn(self.A)
                return cycles
            elif bbb == 6:
                self.C = self.B
                self.update_zn(self.C)
                return cycles
            elif bbb == 7:
                self.B = self.C
                self.update_zn(self.B)
                return cycles
            else:
                raise Exception(f"MOV inválido: bbb={bbb}")
        
        elif aaa == 1: # INC
            if bbb == 4:  # [DC], incrementa 16 bits
                val = self.get_dc()
                r = (val + 1) & 0xFFFF
                self.set_dc(r)

                # flags
                self.N = int(((r & 0xFF) & 0x80) != 0) # Update N actualiza solo con low byte (C)
                self.Z = int((r & 0xFFFF) == 0) # ZF se actualiza solo en DC = $0000. No se toca CF.
                cycles = 3
            else:
                reg = reg_names[bbb]
                val = self.get_reg(reg)
                r = val + 1
                r = r & 0xFF
                self.set_overflow_add(val, 1, r)
                self.set_reg(reg, r)
                self.update_zn(r)
                cycles = 2
            
        elif aaa == 2: # DEC
            if bbb == 4:  # [DC], decrementa 16 bits
                val = self.get_dc()
                r = (val - 1) & 0xFFFF
                self.set_dc(r)
                self.N = int(((r & 0xFF) & 0x80) != 0)
                self.Z = int((r & 0xFFFF) == 0)
                cycles = 3
            else:
                reg = reg_names[bbb]
                val = self.get_reg(reg)
                r = val - 1
                r = r & 0xFF
                self.set_overflow_sub(val, 1, r) # en DEC, si bien es resta, CF no se usa para calcular V
                self.set_reg(reg, r)
                self.update_zn(r)
                cycles = 2

        elif aaa == 3:  # SHIFT / ROTATE

            reg = (bbb >> 2) & 0b1   # el bit de la izquierda define el registro
            op = bbb & 0b11          # los 2 bits de la derecha definen la operacion

            if reg == 0:
                dest = 'A'
            elif reg == 1:
                dest = 'B'
            else:
                raise Exception("SHIFT/ROTATE: registro inválido")

            dst_val = self.get_reg(dest)

            if op == 0:  # SHL
                carry = (dst_val >> 7) & 1
                v = (dst_val << 1) & 0xFF

            elif op == 1:  # SHR
                carry = dst_val & 1
                v = (dst_val >> 1) & 0xFF

            elif op == 2:  # ROL, rotate left with carry
                carry = (dst_val >> 7) & 1
                v = ((dst_val << 1) | self.CF) & 0xFF

            elif op == 3:  # ROR, rotate right with carry
                carry = dst_val & 1
                v = ((dst_val >> 1) | (self.CF << 7)) & 0xFF

            self.set_reg(dest, v)
            self.CF = carry
            self.update_zn(v)
            cycles = 2

        elif aaa == 4:
            if bbb < 4: # NEG
                reg = reg_names[bbb]
                val = self.get_reg(reg)
                r = (0 - val) & 0xFF # Equivale a invertir bits y sumar 1 (complemento a 2)
                self.set_reg(reg, r)
                # El V flag solo se activa si se intenta negar -128 (0x80)
                self.V = (val == 0x80)
                self.CF = (val != 0) # Carry es 1 si el valor original no era 0. Esto es porque se comporta como 0 - val.
                self.update_zn(r)
            elif bbb <= 7: # CLR
                reg = reg_names[bbb-4]
                self.set_reg(reg, 0)
                self.update_zn(0)
                self.V = 0  # Se fuerza V a 0, pero CF no se toca
            cycles = 2

        # Manipulacion de flags
        elif aaa == 5:
            if bbb == 0: self.CF = 0   # CLC
            elif bbb == 1: self.CF = 1 # SEC
            elif bbb == 2: self.V = 0  # CLV
            elif bbb == 4: self.I = 0  # CLI
            elif bbb == 5: self.I = 1  # SEI
            cycles = 2

        elif aaa == 6: # PUSH/PULL
            cycles = 3
            if bbb == 0:
                self.push8(self.A)
            elif bbb == 1:
                self.push8(self.B)
            elif bbb == 2:
                self.push8(self.D)
                self.push8(self.C)
            elif bbb == 3:
                val = self.pack_flags()
                self.push8(val)
            elif bbb == 4:
                self.A = self.pull8()
            elif bbb == 5:
                self.B = self.pull8()
            elif bbb == 6:
                self.C = self.pull8()
                self.D = self.pull8()
            elif bbb == 7:
                val = self.pull8()
                self.unpack_flags(val)

        elif aaa == 7:
            if bbb == 0:  # NOP (No Operación)
                cycles = 1  # El NOP no hace nada, solo consume 1 ciclo

            elif bbb == 2:  # HLT (Halt, pone la CPU en un 'bucle infinito', pero sin bloquear python)
                self.running = False
                #raise StopIteration("CPU HALT")
                self.PC -= 1 # Esto es para trabar el PC en halt, asi el disassembler no muestra lo que sigue en memoria
                cycles = 1
        else:
            raise Exception(f"SPECIAL no implementado: aaa={aaa}, bbb={bbb}")

        return cycles
