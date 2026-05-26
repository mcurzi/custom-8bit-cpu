### 8-bit CPU Emulator - custom ISA
### v1.0

class CPU:
    def __init__(self, memory): # Requires Memory instance as an input
        self.mem = memory.mem   # Direct reference to the bytearray to jump Memory class overhead
        self.memory = memory
        self.irq_pending = False
        self.nmi_pending = False
        self.nmi_line = False
        self.prev_nmi_line = False

        self.reset()  # Reset method has most of the init attributes. There is no reset vector in this CPU. 

    def reset(self):
        # Registros
        self.A = 0
        self.B = 0
        self.C = 0
        self.D = 0

        self.SP = 0xF000  # Stack pointer. By defult is located at 0xF0000 and it's pre-decrement, like 8080 or Z80.
        self.PC = 0x0000  # Program counter, it starts at 0x0000 always on power on and reset. 

        # Flags
        self.Z = 0
        self.N = 0
        self.CF = 0
        self.V = 0
        #self.B = 0  # Reserved, perhaps a future Break flag
        self.I = 1   # I flag = 1 means IRQs disabled by default

        # control
        self.cc = 0
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

    def set_overflow_add(self, a, b, r):  # Detects signed overflow: 127 + 1 = -128, so V = 1
        r = r & 0xFF
        self.V = 1 if ((a ^ r) & (b ^ r) & 0x80) else 0

    def set_overflow_sub(self, a, b, r):
        r = r & 0xFF
        self.V = int(((a ^ b) & (a ^ r) & 0x80) != 0)

    # Group/ungroup flags in 1 byte
    def pack_flags(self):
        byte = 0
        if self.N: byte |= (1 << 7)
        if self.V: byte |= (1 << 6)
        byte |= (1 << 5) # Bit 5 is not used, set to 1
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
        mem = self.mem      # Access to a local variable is much faster than access to an attribute.
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
        mem = self.mem

        self.SP = (self.SP - 1) & 0xFFFF
        addr = self.SP
        mem[addr] = val  # Direct writing, without a method. Does not need '& 0xFF' wrap beacuse mem is a bytearray

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

    # Adressing modes for ALU and MEMORY groups
    # If/Elif blocks are faster than dictionaries and dispatch loops
    def resolve_address(self, bbb):
        mode = bbb
        if mode == 0:  # immediate
            addr = self.PC
            self.PC += 1
            return addr, 1, 'imm'

        if mode == 1:  # absolute
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

        if mode == 6:  # (pointer) + B
            ptr = self.read16(self.PC)
            self.PC += 2
            base = self.read16(ptr)
            addr, cycles = self.compute_indexed(base, self.B, 5)
            return addr, cycles, 'mem'

        if mode == 7:  # [DC+B]
            base = self.get_dc()
            addr, cycles = self.compute_indexed(base, self.B, 3)
            return addr, cycles, 'mem'

    # Fetch-Execute optimized wirh direct readings/writings to memory (not using methods)
    def fetch_operand(self, bbb):
        mem = self.mem  
        addr, cycles, kind = self.resolve_address(bbb)
        if kind == 'imm':
            return mem[addr], None, cycles
        else:
            return mem[addr], addr, cycles

    def step(self):
        if self.nmi_pending:
            self.nmi_pending = False
            self.handle_interrupt(0xFFFA)
            return 7

        elif self.irq_pending and not self.I:
            self.irq_pending = False
            self.handle_interrupt(0xFFFC)
            return 7

        opcode = self.mem[self.PC]
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

        if aaa == 0: # ADC, add with carry. It requires CLC before for additions without carry
            r = self.A + x + self.CF
            self.set_carry(r > 0xFF) # CF = 1 if the result is more than 8 bits (255 or 0xFF)
            r = r & 0xFF
            self.set_overflow_add(self.A, x, r) # does not include the value of CF.
            self.A = r
            self.update_zn(r)
            cycles += 2

        elif aaa == 1:  # SBB, substract with borrow, Z80/8080 style (does not need SEC before, but use CLC for operations w/o borrow)
            new_carry = (x + self.CF) > self.A # Carry flag = 1 if the subthraend (x + CF) is larger than A (borrow)
            r = self.A - x - self.CF
            r = r & 0xFF # ensures that r is 8 bits
            self.set_carry(new_carry)
            self.set_overflow_sub(self.A, x + self.CF, r) # Here, by definition, the subtrahend includes CF value.
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

        elif aaa == 5:  # CMP (Compare A with sth)
            r = self.A - x
            r = r & 0xFF 
            self.Z = int((r & 0xFF) == 0)
            self.N = int((r & 0x80) != 0)
            self.CF = int(self.A < x)           # CF = 1 if there is borrow (A < x), this is 8080/Z80 style
            self.set_overflow_sub(self.A, x, r) # CMP is substraction without implicit borrow (just x, not x + CF)
            cycles += 2

        elif aaa == 6:  # CPB (Compare B with sth)
            r = self.B - x
            r = r & 0xFF
            self.Z = int((r & 0xFF) == 0)
            self.N = int((r & 0x80) != 0)
            self.CF = int(self.B < x)
            self.set_overflow_sub(self.B, x, r)
            cycles += 2

        elif aaa == 7:  # CPC (Compare C with sth)
            r = self.C - x
            r = r & 0xFF
            self.Z = int((r & 0xFF) == 0)
            self.N = int((r & 0x80) != 0)
            self.CF = int(self.C < x)
            self.set_overflow_sub(self.C, x, r)
            cycles += 2
        return cycles

    ### MEMORY GROUP (CC=01)
    def exec_mem(self, aaa, bbb):
    
        mem = self.mem

        if aaa < 4:  # LOAD
            v, addr, cycles = self.fetch_operand(bbb)
            if aaa == 0: self.A = v; self.update_zn(self.A)
            elif aaa == 1: self.B = v; self.update_zn(self.B)
            elif aaa == 2: self.C = v; self.update_zn(self.C)
            elif aaa == 3: self.D = v; self.update_zn(self.D)
            cycles += 2
        else:  # STORE
            if bbb == 0:
                raise Exception("STORE does not support inmediate mode")
            else:
                if aaa == 4: val = self.A
                elif aaa == 5: val = self.B
                elif aaa == 6: val = self.C
                elif aaa == 7: val = self.D
                
                addr, cycles, _ = self.resolve_address(bbb)
                cycles += 2
                
                mem[addr] = val

        return cycles

    ### FLOW GROUP (CC=10)
    def exec_flow(self, aaa, bbb):
        if bbb == 0: cond = True
        elif bbb == 1: cond = bool(self.Z)
        elif bbb == 2: cond = not bool(self.Z)
        elif bbb == 3: cond = bool(self.N)
        elif bbb == 4: cond = not bool(self.N)
        elif bbb == 5: cond = bool(self.CF)
        elif bbb == 6: cond = not bool(self.CF)
        elif bbb == 7: cond = bool(self.V)

        if aaa == 2 or aaa == 3:
            offset = self.mem[self.PC]
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
        else: raise Exception(f"FLOW not implemented: aaa={aaa}, bbb={bbb}")

### SPECIAL GROUP (CC=11)
    def exec_special(self, aaa, bbb):
        cycles = 0

        if aaa == 0:  # MOV
            cycles = 2
            if bbb == 0: # MOV A,B (origin,destination)
                self.B = self.A
                self.update_zn(self.B)
            elif bbb == 1:
                self.C = self.A
                self.update_zn(self.C)
            if bbb == 2:
                self.D = self.A
                self.update_zn(self.D)
            elif bbb == 3: # MOV B,A
                self.A = self.B
                self.update_zn(self.A)
            elif bbb == 4:
                self.A = self.C
                self.update_zn(self.A)
            elif bbb == 5:
                self.A = self.D
                self.update_zn(self.A)
            elif bbb == 6:
                self.C = self.B
                self.update_zn(self.C)
            elif bbb == 7:
                self.B = self.C
                self.update_zn(self.B)

        elif aaa == 1: # INC
            if bbb == 4:  # [DC], increments 16 bits
                val = (self.D << 8) | self.C
                r = (val + 1) & 0xFFFF
                self.C = r & 0xFF
                self.D = (r >> 8) & 0xFF
                # update flags
                self.N = int(((r & 0xFF) & 0x80) != 0) # N flag updates only with low byte (C)
                self.Z = int((r & 0xFFFF) == 0) # ZF updates only with DC = $0000. CF is not updated.
                cycles = 3
            else:
                if bbb == 0: val = self.A; self.A = r = (val + 1) & 0xFF
                elif bbb == 1: val = self.B; self.B = r = (val + 1) & 0xFF
                elif bbb == 2: val = self.C; self.C = r = (val + 1) & 0xFF
                elif bbb == 3: val = self.D; self.D = r = (val + 1) & 0xFF
                else: raise Exception(f"SPECIAL not implemented: aaa={aaa}, bbb={bbb}")

                self.set_overflow_add(val, 1, r)
                self.update_zn(r)
                cycles = 2

        elif aaa == 2: # DEC
            if bbb == 4:  # [DC], decrements 16 bits
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
                else: raise Exception(f"SPECIAL not implemented: aaa={aaa}, bbb={bbb}")

                self.set_overflow_sub(val, 1, r) # CF is not used to calculate V in DEC
                self.update_zn(r)
                cycles = 2

        elif aaa == 3:  # SHIFT / ROTATE
            reg_idx = (bbb >> 2) & 0b1   # the left bit defines de register (A or B)
            op = bbb & 0b11              # the 2 bits on the right define the operation

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

            # Set the result in the correct registry
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

                # V flag is only activated if trying to do the negative of -128 (0x80)
                self.V = (val == 0x80)
                self.CF = (val != 0) # CF = 1 if the original value is not 0, beacuse it behaves as 0 - val.
                self.update_zn(r)
            elif bbb <= 7: # CLR
                r = 0
                if bbb == 4: self.A = 0
                elif bbb == 5: self.B = 0
                elif bbb == 6: self.C = 0
                elif bbb == 7: self.D = 0

                self.update_zn(0)
                self.V = 0  # V flag is forced to 0, but CF does not change
            cycles = 2

        # Flags control
        elif aaa == 5:
            if bbb == 0: self.CF = 0   # CLC
            elif bbb == 1: self.CF = 1 # SEC
            elif bbb == 2: self.V = 0  # CLV
            elif bbb == 4: self.I = 0  # CLI
            elif bbb == 5: self.I = 1  # SEI
            else: raise Exception(f"SPECIAL not implemented: aaa={aaa}, bbb={bbb}")
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
            if bbb == 0:  # NOP (No OPeration)
                cycles = 1  # Consumes 1 cycle

            elif bbb == 1:  # LSP, load stack pointer
                self.SP = self.mem[self.PC] | (self.mem[(self.PC + 1) & 0xFFFF] << 8)
                self.PC = (self.PC + 2) & 0xFFFF
                cycles = 3

            elif bbb == 2:  # HLT, disables execution logic, without blocking python)
                self.running = False
                # Keeps program counter in HLT instruction, this is not realistic, but it's used to prevent
                # PC passing HLT instruction in cycle batches or with the Step button in the UI.
                self.PC = (self.PC - 1) & 0xFFFF
                cycles = 1
            
            else:
                raise Exception(f"SPECIAL not implemented: aaa={aaa}, bbb={bbb}")

        return cycles


