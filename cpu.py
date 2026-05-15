### 8-bit CPU Emulator - custom ISA
### v1.0

### Clase de Memoria
class Memory:
    def __init__(self):
        self.mem = bytearray(65536)  # 64 KB


### CPU
class CPU:
    def __init__(self, memory: Memory): # Recibe instancia de Memory como input al ser creada
        self.mem = memory.mem   #Referencia directa al bytearray para saltar el overhead de la clase Memory
        self.mem_meta = memory         # acceso a last_write
        self.memory = memory
        self.irq_pending = False
        self.nmi_pending = False
        self.nmi_line = False
        self.prev_nmi_line = False
        self.last_write=None

        self.reset()  # reutiliza lógica, el reset apunta el PC directo al inicio del programa, no es un vector.

    def reset(self):
        # Registros
        self.A = 0
        self.B = 0
        self.C = 0
        self.D = 0

        self.SP = 0xF000  # Stack pointer. El stack usa memoria justo antes del framebuffer ($6000). Va hacia atras, por eso no la pisa.

        # Program counter inicia siempre en 0x100. El Z80 hace algo asi pero en 0x0000
        self.PC = 0x0000   # Program counter, el reset lo ubica en $00, acá debe cargarse la primera instruccion

        # Flags
        self.Z = 0
        self.N = 0
        self.CF = 0
        self.V = 0
        #self.B = 0  # Reservado para break flag
        self.I = 1  # IRQ deshabilitadas por defecto

        # control
        self.cc = 0
        # Running, es para el debugger y para la UI
        self.running = False

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
        r = r & 0xFF
        self.V = 1 if ((a ^ r) & (b ^ r) & 0x80) else 0

    def set_overflow_sub(self, a, b, r):
        r = r & 0xFF
        self.V = int(((a ^ b) & (a ^ r) & 0x80) != 0)

    # Agrupar/desagrupar flags en 1 byte
    def pack_flags(self):
        byte = 0
        if self.N: byte |= (1 << 7)
        if self.V: byte |= (1 << 6)
        byte |= (1 << 5) # Bit 5, no se usa, se fija en 1
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

    ### Memory helpers optimizdos
    def read16(self, addr):
        # Acceso directo al buffer mem
        mem = self.mem
        return mem[addr & 0xFFFF] | (mem[(addr + 1) & 0xFFFF] << 8)

    def compute_indexed(self, base, index, base_cycles):
        lo = (base & 0xFF) + index
        carry = lo > 0xFF  # page crossing
        addr = ((base & 0xFF00) | (lo & 0xFF))
        cycles = base_cycles
        if carry:
            addr = (addr + 0x100) & 0xFFFF
            cycles += 1
        return addr, cycles

    def get_reg(self, r):
        return getattr(self, r)

    def set_reg(self, r, v):
        return setattr(self, r, v & 0xFF)

    #Stack helpers
    def push8(self, val):    
        mem = self.mem                #Versiones locales de variables de memoria son mas rapidas
        meta = self.mem_meta

        self.SP = (self.SP - 1) & 0xFFFF
        addr = self.SP
        mem[addr] = val  # Escritura directa, no precisa el wrap & 0xFF porque es un bytearray
        meta.last_write = self.SP

    def pull8(self):
        val = self.mem[self.SP] # Lectura directa
        self.SP = (self.SP + 1) & 0xFFFF
        return val

    def push16(self, val):
        self.push8((val >> 8) & 0xFF)
        self.push8(val & 0xFF)

    def pull16(self):
        lo = self.pull8()
        hi = self.pull8()
        return lo | (hi << 8)

    def handle_interrupt(self, vector_addr):
        self.push16(self.PC)
        self.push8(self.pack_flags())
        self.I = 1
        self.PC = self.read16(vector_addr)

    def request_irq(self):
        self.irq_pending = True

    def set_nmi_line(self, state):
        if state and not self.prev_nmi_line:
            self.nmi_pending = True
        self.prev_nmi_line = state
        self.nmi_line = state

    # Adressing - OPTIMIZADO
    def resolve_address(self, bbb):
        mode = bbb
        if mode == 0:  # inmediato
            addr = self.PC
            self.PC += 1
            return addr, 1, 'imm'

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
            return self.mem[addr], None, cycles # Lectura directa
        else:
            return self.mem[addr], addr, cycles # Lectura directa

    def step(self):
        if self.nmi_pending:
            self.nmi_pending = False
            self.handle_interrupt(0xFFFA)
            return 7

        elif self.irq_pending and not self.I:
            self.irq_pending = False
            self.handle_interrupt(0xFFFC)
            return 7

        # Fetch-Execute OPTIMIZADO
        opcode = self.mem[self.PC] # Lectura directa
        self.PC = (self.PC + 1) & 0xFFFF
        aaa = (opcode >> 5) & 0b111
        bbb = (opcode >> 2) & 0b111
        self.cc = opcode & 0b11

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

        return cycles

    def advance_cycles(self, cycle_count):
        cycles_left = cycle_count
        while cycles_left > 0:
            cycles_spent = self.step()
            cycles_left -= cycles_spent
        return cycle_count - cycles_left

    ### ALU GROUP (CC=00)
    def exec_alu(self, aaa, bbb):
        x, _, cycles = self.fetch_operand(bbb)

        if aaa == 0: # ADC, add with carry, asegurar CLC antes para sumar sin carry
            r = self.A + x + self.CF
            self.set_carry(r > 0xFF) # El carry se activa si el resultado total supera los 8 bits (255)
            r = r & 0xFF
            self.set_overflow_add(self.A, x, r) # no incluye valor de CF.
            self.A = r # Acceso directo a registro
            self.update_zn(r)
            cycles += 2

        elif aaa == 1:  # SBB, substract with borrow estilo Z80/8080 (no necesita SEC antes, asegurar CLC para restas sin borrow)
            new_carry = (x + self.CF) > self.A # El Carry se activa si todo lo que se resta (x + CF) es mayor que A (hubo préstamo)
            r = self.A - x - self.CF
            r = r & 0xFF #asegurar que el registro sea de 8 bits
            self.set_carry(new_carry)
            self.set_overflow_sub(self.A, x + self.CF, r) # Acá si el sustraendo incluye valor de CF.
            self.A = r
            self.update_zn(r)
            cycles += 2
        elif aaa == 2:  # AND
            r = self.A & x
            self.A = r
            self.update_zn(r)
            cycles += 1

        elif aaa == 3:  # ORA
            r = self.A| x
            self.A = r
            self.update_zn(r)
            cycles += 1

        elif aaa == 4:  # XOR
            r = self.A ^ x
            self.A = r
            self.update_zn(r)
            cycles += 1

        elif aaa == 5:  # CMP (Compara A)
            r = self.A - x
            r = r & 0xFF # Fuerza a 8 bits
            self.Z = int((r & 0xFF) == 0)
            self.N = int((r & 0x80) != 0)
            self.CF = int(self.A < x)      # 1 si hay préstamo (A < x), estilo 8080/Z80
            self.set_overflow_sub(self.A, x, r) # CMP es resta pura, sin borrow implicito (el sustraendo es solo x, no x + CF)
            cycles += 2

        elif aaa == 6:  # CPB (Compara B)
            r = self.B - x
            r = r & 0xFF
            self.Z = int((r & 0xFF) == 0)
            self.N = int((r & 0x80) != 0)
            self.CF = int(self.B < x)
            self.set_overflow_sub(self.B, x, r)
            cycles += 2

        elif aaa == 7:  # CPC (Compara C)
            r = self.C - x
            r = r & 0xFF
            self.Z = int((r & 0xFF) == 0)
            self.N = int((r & 0x80) != 0)
            self.CF = int(self.C < x)
            self.set_overflow_sub(self.C, x, r)
            cycles += 2
        return cycles

    ### MEMORY GROUP (CC=01) - OPTIMIZADO
    def exec_mem(self, aaa, bbb):
    
        mem = self.mem   # Acceder a una variable local es mucho más rápido que acceder a un atributo.
        meta = self.mem_meta

        if aaa < 4:  # LOAD
            v, addr, cycles = self.fetch_operand(bbb)
            if aaa == 0: self.A = v; self.update_zn(self.A)
            elif aaa == 1: self.B = v; self.update_zn(self.B)
            elif aaa == 2: self.C = v; self.update_zn(self.C)
            elif aaa == 3: self.D = v; self.update_zn(self.D)
            cycles += 2
        else:  # STORE
            if bbb == 0:
                raise Exception("STORE no soporta inmediato")
            else:
                # ESCRITURA DIRECTA AL BUFFER:
                if aaa == 4: val = self.A
                elif aaa == 5: val = self.B
                elif aaa == 6: val = self.C
                elif aaa == 7: val = self.D
                
                addr, cycles, _ = self.resolve_address(bbb)
                cycles += 2
                
                mem[addr] = val
                meta.last_write = addr

        return cycles

    ### FLOW GROUP (CC=10) - OPTIMIZADO
    def exec_flow(self, aaa, bbb):
        # ... (lógica de cond intacta) ...
        if bbb == 0: cond = True
        elif bbb == 1: cond = bool(self.Z)
        elif bbb == 2: cond = not bool(self.Z)
        elif bbb == 3: cond = bool(self.N)
        elif bbb == 4: cond = not bool(self.N)
        elif bbb == 5: cond = bool(self.CF)
        elif bbb == 6: cond = not bool(self.CF)
        elif bbb == 7: cond = bool(self.V)

        if aaa == 2 or aaa == 3:
            offset = self.mem[self.PC] # Lectura directa
            self.PC = (self.PC + 1) & 0xFFFF
            if offset & 0x80: offset -= 0x100
            if not cond: return 2
            elif aaa == 2: # BRA
                self.PC = (self.PC + offset) & 0xFFFF
                return 3
            elif aaa == 3: # BSR
                self.push16(self.PC)
                self.PC = (self.PC + offset) & 0xFFFF
                return 5
        elif 0 <= aaa <= 2:
            addr = self.read16(self.PC)
            self.PC = (self.PC + 2) & 0xFFFF
            if not cond: return 2
            elif aaa == 0: self.PC = addr; return 3
            elif aaa == 1: self.push16(self.PC); self.PC = addr; return 5
        elif aaa == 4: self.PC = self.pull16(); return 5
        elif aaa == 5:
            flags = self.pull8()
            self.unpack_flags(flags)
            self.PC = self.pull16()
            return 6
        return 0

### SPECIAL GROUP (CC=11)
    def exec_special(self, aaa, bbb):
        cycles = 0

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
                val = (self.D << 8) | self.C
                r = (val + 1) & 0xFFFF
                self.C = r & 0xFF
                self.D = (r >> 8) & 0xFF
                # flags
                self.N = int(((r & 0xFF) & 0x80) != 0) # Update N actualiza solo con low byte (C)
                self.Z = int((r & 0xFFFF) == 0) # ZF se actualiza solo en DC = $0000. No se toca CF.
                cycles = 3
            else:
                # Acceso directo por bbb sin pasar por reg_names
                if bbb == 0: val = self.A; self.A = r = (val + 1) & 0xFF
                elif bbb == 1: val = self.B; self.B = r = (val + 1) & 0xFF
                elif bbb == 2: val = self.C; self.C = r = (val + 1) & 0xFF
                elif bbb == 3: val = self.D; self.D = r = (val + 1) & 0xFF

                self.set_overflow_add(val, 1, r)
                self.update_zn(r)
                cycles = 2

        elif aaa == 2: # DEC
            if bbb == 4:  # [DC], decrementa 16 bits
                val = (self.D << 8) | self.C
                r = (val - 1) & 0xFFFF
                self.C = r & 0xFF
                self.D = (r >> 8) & 0xFF
                self.N = int(((r & 0xFF) & 0x80) != 0)
                self.Z = int((r & 0xFFFF) == 0)
                cycles = 3
            else:
                if bbb == 0: val = self.A; self.A = r = (val - 1) & 0xFF
                elif bbb == 1: val = self.B; self.B = r = (val - 1) & 0xFF
                elif bbb == 2: val = self.C; self.C = r = (val - 1) & 0xFF
                elif bbb == 3: val = self.D; self.D = r = (val - 1) & 0xFF

                self.set_overflow_sub(val, 1, r) # en DEC, si bien es resta, CF no se usa para calcular V
                self.update_zn(r)
                cycles = 2

        elif aaa == 3:  # SHIFT / ROTATE
            reg_idx = (bbb >> 2) & 0b1   # el bit de la izquierda define el registro
            op = bbb & 0b11          # los 2 bits de la derecha definen la operacion

            dst_val = self.A if reg_idx == 0 else self.B

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

            # Asignación de vuelta
            if reg_idx == 0: self.A = v
            else: self.B = v

            self.CF = carry
            self.update_zn(v)
            cycles = 2

        elif aaa == 4:
            if bbb < 4: # NEG
                if bbb == 0: val = self.A; self.A = r = (0 - val) & 0xFF
                elif bbb == 1: val = self.B; self.B = r = (0 - val) & 0xFF
                elif bbb == 2: val = self.C; self.C = r = (0 - val) & 0xFF
                elif bbb == 3: val = self.D; self.D = r = (0 - val) & 0xFF

                # El V flag solo se activa si se intenta negar -128 (0x80)
                self.V = (val == 0x80)
                self.CF = (val != 0) # Carry es 1 si el valor original no era 0. Esto es porque se comporta como 0 - val.
                self.update_zn(r)
            elif bbb <= 7: # CLR
                r = 0
                if bbb == 4: self.A = 0
                elif bbb == 5: self.B = 0
                elif bbb == 6: self.C = 0
                elif bbb == 7: self.D = 0

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

            elif bbb == 1:  # LSP, load stack pointer
                # Optimización: lectura directa de memoria
                self.SP = self.mem[self.PC] | (self.mem[(self.PC + 1) & 0xFFFF] << 8)
                self.PC = (self.PC + 2) & 0xFFFF
                cycles = 3

            elif bbb == 2:  # HLT (Halt, pone la CPU en un 'bucle infinito', pero sin bloquear python)
                self.running = False
                #raise StopIteration("CPU HALT")
                self.PC = (self.PC - 1) & 0xFFFF # Esto es para trabar el PC en halt, asi el disassembler no muestra lo que sigue en memoria
                cycles = 1
        else:
            raise Exception(f"SPECIAL no implementado: aaa={aaa}, bbb={bbb}")

        return cycles


