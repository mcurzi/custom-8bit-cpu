### 8-bit CPU Emulator - custom ISA
### v1.1

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
        self.I = 1

        # control
        self.cc = 0
        self.running = False

    # Flags pack/unpack
    def pack_flags(self):
        return (self.N << 7) | (self.V << 6) | (1 << 5) | (self.I << 2) | (self.Z << 1) | self.CF

    def unpack_flags(self, byte):
        self.N = (byte >> 7) & 1
        self.V = (byte >> 6) & 1
        self.I = (byte >> 2) & 1
        self.Z = (byte >> 1) & 1
        self.CF = byte & 1

    ## Memory helpers optimized
    def read16(self, addr):
        mem = self.mem
        return mem[addr & 0xFFFF] | (mem[(addr + 1) & 0xFFFF] << 8)

    def compute_indexed(self, base, index, base_cycles):
        lo = (base & 0xFF) + index
        carry = lo > 0xFF
        addr = ((base & 0xFF00) | (lo & 0xFF))
        if carry:
            addr = (addr + 0x100) & 0xFFFF
            return addr, base_cycles + 1
        return addr, base_cycles

    # Stack helpers
    def push8(self, val):
        self.SP = (self.SP - 1) & 0xFFFF
        self.mem[self.SP] = val  # Direct writing, without a method. Does not need '& 0xFF' wrap because mem is a bytearray

    def pull8(self):
        val = self.mem[self.SP] # Lectura directa
        self.SP = (self.SP + 1) & 0xFFFF
        return val

    def push16(self, val):
        mem = self.mem
        sp = self.SP
        # Saves HI in SP-1, then LO in SP-2
        mem[(sp - 1) & 0xFFFF] = (val >> 8) & 0xFF
        mem[(sp - 2) & 0xFFFF] = val & 0xFF
        self.SP = (sp - 2) & 0xFFFF

    def pull16(self):
        mem = self.mem
        sp = self.SP
        lo = mem[sp]
        hi = mem[(sp + 1) & 0xFFFF]
        self.SP = (sp + 2) & 0xFFFF
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

    # Resolve addresss with inline instructions for more speed
    def resolve_address(self, bbb):
        pc = self.PC
        if bbb == 0:  # Immediate
            self.PC = (pc + 1) & 0xFFFF
            return pc, 1

        mem = self.mem
        if bbb == 1:  # Absolute
            addr = mem[pc] | (mem[(pc + 1) & 0xFFFF] << 8)
            self.PC = (pc + 2) & 0xFFFF
            return addr, 2

        if bbb == 2:  # Abs + B
            base = mem[pc] | (mem[(pc + 1) & 0xFFFF] << 8)
            self.PC = (pc + 2) & 0xFFFF
            addr, cycles = self.compute_indexed(base, self.B, 3)
            return addr, cycles

        if bbb == 3:  # Abs + C
            base = mem[pc] | (mem[(pc + 1) & 0xFFFF] << 8)
            self.PC = (pc + 2) & 0xFFFF
            addr, cycles = self.compute_indexed(base, self.C, 3)
            return addr, cycles

        if bbb == 4:  # [DC]
            return ((self.D << 8) | self.C), 2

        if bbb == 5:  # Indirect
            ptr = mem[pc] | (mem[(pc + 1) & 0xFFFF] << 8)
            self.PC = (pc + 2) & 0xFFFF
            addr = mem[ptr] | (mem[(ptr + 1) & 0xFFFF] << 8)
            return addr, 4

        if bbb == 6:  # (Pointer) + B
            ptr = mem[pc] | (mem[(pc + 1) & 0xFFFF] << 8)
            self.PC = (pc + 2) & 0xFFFF
            base = mem[ptr] | (mem[(ptr + 1) & 0xFFFF] << 8)
            addr, cycles = self.compute_indexed(base, self.B, 5)
            return addr, cycles

        if bbb == 7:  # [DC + B]
            base = (self.D << 8) | self.C
            addr, cycles = self.compute_indexed(base, self.B, 3)
            return addr, cycles

    def step(self):
        if self.nmi_pending:
            self.nmi_pending = False
            self.handle_interrupt(0xFFFA)
            return 7

        if self.irq_pending and not self.I:
            self.irq_pending = False
            self.handle_interrupt(0xFFFC)
            return 7

        opcode = self.mem[self.PC]
        self.PC = (self.PC + 1) & 0xFFFF

        aaa = (opcode >> 5) & 0b111
        bbb = (opcode >> 2) & 0b111
        cc = opcode & 0b11

        if cc == 0b00: return self.exec_alu(aaa, bbb)
        if cc == 0b01: return self.exec_mem(aaa, bbb)
        if cc == 0b10: return self.exec_flow(aaa, bbb)
        return self.exec_special(aaa, bbb)

    # Fetch operand inline inside group methods for more speed
    def exec_alu(self, aaa, bbb):
        mem = self.mem
        addr, cycles = self.resolve_address(bbb)
        x = mem[addr]

        if aaa == 0:  # ADC, add with carry. It requires CLC before for additions without carry
            r = self.A + x + self.CF
            self.CF = 1 if r > 0xFF else 0  # CF = 1 if the result is more than 8 bits (255 or 0xFF)
            r &= 0xFF
            self.V = ((self.A ^ r) & (x ^ r) & 0x80) >> 7  # does not include the value of CF.
            self.A = r
            self.Z = 1 if r == 0 else 0
            self.N = r >> 7
            return cycles + 2

        if aaa == 1:  # SBB, substract with borrow, Z80/8080 style (does not need SEC before, but use CLC for operations w/o borrow)
            new_carry = (x + self.CF) > self.A  # Carry flag = 1 if the subthraend (x + CF) is larger than A (borrow)
            r = (self.A - x - self.CF) & 0xFF
            self.V = ((self.A ^ ((x + self.CF) & 0xFF)) & (self.A ^ r) & 0x80) >> 7  # Here, by definition, the subtrahend includes CF value.
            self.CF = 1 if new_carry else 0
            self.A = r
            self.Z = 1 if r == 0 else 0
            self.N = r >> 7
            return cycles + 2

        if aaa == 2:  # AND
            self.A &= x
            self.Z = 1 if self.A == 0 else 0
            self.N = self.A >> 7
            return cycles + 1

        if aaa == 3:  # ORA
            self.A |= x
            self.Z = 1 if self.A == 0 else 0
            self.N = self.A >> 7
            return cycles + 1

        if aaa == 4:  # XOR
            self.A ^= x
            self.Z = 1 if self.A == 0 else 0
            self.N = self.A >> 7
            return cycles + 1

        elif aaa == 5:  # CMP (Compare A with sth)
            r = (self.A - x) & 0xFF
            self.Z = 1 if r == 0 else 0
            self.N = r >> 7
            self.CF = 1 if self.A < x else 0          # CF = 1 if there is borrow (A < x), this is 8080/Z80 style
            self.V = ((self.A ^ x) & (self.A ^ r) & 0x80) >> 7 # CMP is substraction without implicit borrow (just x, not x + CF)
            return cycles + 2

        elif aaa == 6:  # CPB (Compare B with sth)
            r = (self.B - x) & 0xFF
            self.Z = 1 if r == 0 else 0
            self.N = r >> 7
            self.CF = 1 if self.A < x else 0
            self.V = ((self.A ^ x) & (self.A ^ r) & 0x80) >> 7
            return cycles + 2

        elif aaa == 7:  # CPC (Compare C with sth)
            r = (self.C - x) & 0xFF
            self.Z = 1 if r == 0 else 0
            self.N = r >> 7
            self.CF = 1 if self.A < x else 0
            self.V = ((self.A ^ x) & (self.A ^ r) & 0x80) >> 7
            return cycles + 2


    ### MEMORY GROUP (CC=01)
    def exec_mem(self, aaa, bbb):
        mem = self.mem

        if aaa < 4:  # LOAD
            addr, cycles = self.resolve_address(bbb)
            v = mem[addr]

            if aaa == 0: self.A = v
            elif aaa == 1: self.B = v
            elif aaa == 2: self.C = v
            elif aaa == 3: self.D = v

            self.Z = 1 if v == 0 else 0
            self.N = (v >> 7) & 1
            cycles += 2

        else:  # STORE
            if bbb == 0:
                raise Exception("STORE does not support inmediate mode")
            else:
                if aaa == 4: val = self.A
                elif aaa == 5: val = self.B
                elif aaa == 6: val = self.C
                elif aaa == 7: val = self.D

                addr, cycles = self.resolve_address(bbb)
                mem[addr] = val
                cycles += 2

        return cycles

### FLOW GROUP (CC=10)
    def exec_flow(self, aaa, bbb):
        if bbb == 0: cond = True
        elif bbb == 1: cond = self.Z
        elif bbb == 2: cond = not self.Z
        elif bbb == 3: cond = self.N
        elif bbb == 4: cond = not self.N
        elif bbb == 5: cond = self.CF
        elif bbb == 6: cond = not self.CF
        elif bbb == 7: cond = self.V

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
            elif aaa == 0:   # JMP
                self.PC = addr
                return 3
            elif aaa == 1:   # JSR
                self.push16(self.PC)
                self.PC = addr
                return 5
        elif aaa == 4:   # RET
            self.PC = self.pull16()
            return 5
        elif aaa == 5:   # RTI
            self.unpack_flags(self.pull8())
            self.PC = self.pull16()
            return 6
        else: raise Exception(f"FLOW not implemented: aaa={aaa}, bbb={bbb}")

### SPECIAL GROUP (CC=11)
    def exec_special(self, aaa, bbb):
        cycles = 0

        if aaa == 0:  # MOV
            cycles = 2

            if bbb == 0:      # A -> B
                v = self.A
                self.B = v
            elif bbb == 1:    # A -> C
                v = self.A
                self.C = v
            elif bbb == 2:    # A -> D
                v = self.A
                self.D = v
            elif bbb == 3:    # B -> A
                v = self.B
                self.A = v
            elif bbb == 4:    # C -> A
                v = self.C
                self.A = v
            elif bbb == 5:    # D -> A
                v = self.D
                self.A = v
            elif bbb == 6:    # B -> C
                v = self.B
                self.C = v
            elif bbb == 7:    # C -> B
                v = self.C
                self.B = v

            self.Z = 1 if v == 0 else 0
            self.N = v >> 7

        elif aaa == 1: # INC
            if bbb == 4:  # [DC], increments 16 bits
                val = (self.D << 8) | self.C
                r = (val + 1) & 0xFFFF
                self.C = r & 0xFF
                self.D = (r >> 8) & 0xFF
                # update flags
                self.N = (r & 0x80) >> 7 # N flag updates only with low byte (C)
                self.Z = 1 if r == 0 else 0  # ZF updates only with DC = $0000. CF is not updated.
                cycles = 3
            else:
                if bbb == 0: val = self.A; self.A = r = (val + 1) & 0xFF
                elif bbb == 1: val = self.B; self.B = r = (val + 1) & 0xFF
                elif bbb == 2: val = self.C; self.C = r = (val + 1) & 0xFF
                elif bbb == 3: val = self.D; self.D = r = (val + 1) & 0xFF
                else: raise Exception(f"SPECIAL not implemented: aaa={aaa}, bbb={bbb}")

                self.V = 1 if (val == 0x7F) else 0
                self.Z = 1 if r == 0 else 0
                self.N = r >> 7
                cycles = 2

        elif aaa == 2: # DEC
            if bbb == 4:  # [DC], decrements 16 bits
                val = (self.D << 8) | self.C
                r = (val - 1) & 0xFFFF
                self.C = r & 0xFF
                self.D = r >> 8
                self.N = (r & 0x80) >> 7
                self.Z = 1 if r == 0 else 0
                cycles = 3
            else:
                if bbb == 0: val = self.A; self.A = r = (val - 1) & 0xFF
                elif bbb == 1: val = self.B; self.B = r = (val - 1) & 0xFF
                elif bbb == 2: val = self.C; self.C = r = (val - 1) & 0xFF
                elif bbb == 3: val = self.D; self.D = r = (val - 1) & 0xFF
                else: raise Exception(f"SPECIAL not implemented: aaa={aaa}, bbb={bbb}")

                self.V = 1 if (val == 0x80) else 0
                self.Z = 1 if r == 0 else 0
                self.N = r >> 7
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
                v = (dst_val >> 1) | (self.CF << 7)

            # Set the result in the correct registry
            if reg_idx == 0: self.A = v
            else: self.B = v

            self.CF = carry
            self.Z = 1 if v == 0 else 0
            self.N = (v >> 7) & 1
            cycles = 2

        elif aaa == 4:
            if bbb < 4: # NEG
                if bbb == 0: val = self.A; self.A = r = (0 - val) & 0xFF
                elif bbb == 1: val = self.B; self.B = r = (0 - val) & 0xFF
                elif bbb == 2: val = self.C; self.C = r = (0 - val) & 0xFF
                elif bbb == 3: val = self.D; self.D = r = (0 - val) & 0xFF

                # V flag is only activated if trying to do the negative of -128 (0x80)
                self.V = 1 if (val == 0x80) else 0
                self.CF = 1 if (val != 0) else 0  # CF = 1 if the original value is not 0, beacuse it behaves as 0 - val.
                self.Z = 1 if r == 0 else 0
                self.N = r >> 7
            elif bbb <= 7: # CLR
                r = 0
                if bbb == 4: self.A = 0
                elif bbb == 5: self.B = 0
                elif bbb == 6: self.C = 0
                elif bbb == 7: self.D = 0

                self.Z = 1
                self.N = 0
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
            if bbb == 0: self.push8(self.A)
            elif bbb == 1: self.push8(self.B)
            elif bbb == 2:
                self.push8(self.D)
                self.push8(self.C)
            elif bbb == 3: self.push8(self.pack_flags())
            elif bbb == 4: self.A = self.pull8()
            elif bbb == 5: self.B = self.pull8()
            elif bbb == 6:
                self.C = self.pull8()
                self.D = self.pull8()
            elif bbb == 7: self.unpack_flags(self.pull8())

        elif aaa == 7:
            if bbb == 0:  # NOP (No OPeration)
                cycles = 1  # Consumes 1 cycle

            elif bbb == 1:  # LSP, load stack pointer
                self.SP = self.read16(self.PC)
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
