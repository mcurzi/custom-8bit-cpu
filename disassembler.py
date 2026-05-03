# Disassembler:

ALU_NAMES = ["ADC", "SBB", "AND", "ORA", "XOR", "CMP", "CPB", "CPC"]

LOAD_NAMES = ["LDA", "LDB", "LDC", "LDD", "STA", "STB", "STC", "STD"]

FLOW_NAMES = ["JMP", "JSR", "BRA", "BSR", "RET", "RTI", "???", "???"]

REG_NAMES = ["A", "B", "C", "D", "[DC]"]

REG_REG_NAMES = ["A,B", "A,C", "A,D", "B,A", "C,A", "D,A", "B,C", "C,B"]

COND_NAMES = ["UN", "ZF", "NZ", "NF", "NN", "CF", "NC", "VF"]

SHIFT_NAMES = ["SHL A", "SHR A", "ROL A", "ROR A", "SHL B", "SHR B", "ROL B", "ROR B"]

STACK_NAMES = ["PSH A", "PSH B", "PSH DC", "PSH FL", "PLL A", "PLL B", "PLL DC", "PLL FL"]


def disassemble_at(memory, addr):
    op = memory.read(addr)

    aaa = (op >> 5) & 7
    bbb = (op >> 2) & 7
    cc  = op & 3

    mnemonic = "???"
    operand = ""
    size = 1

    ### ALU y LOAD/STORE
    if cc in [0,1]:
        ### ALU
        if cc == 0:
            mnemonic = ALU_NAMES[aaa]
        ### LOAD / STORE
        elif cc == 1:
            mnemonic = LOAD_NAMES[aaa]

        mode = bbb

        if mode == 0:  # inmediato
            val = memory.read(addr + 1)
            operand = f"#${val:02X}"
            size = 2

        elif mode == 1:  # absoluto
            lo = memory.read(addr + 1)
            hi = memory.read(addr + 2)
            operand = f"${(hi<<8|lo):04X}"
            size = 3

        elif mode == 2:  # abs,B
            lo = memory.read(addr + 1)
            hi = memory.read(addr + 2)
            operand = f"${(hi<<8|lo):04X},B"
            size = 3

        elif mode == 3:  # abs,C
            lo = memory.read(addr + 1)
            hi = memory.read(addr + 2)
            operand = f"${(hi<<8|lo):04X},C"
            size = 3

        elif mode == 4:
            operand = "[DC]"
            size = 1
                
        elif mode == 5: # ind
            lo = memory.read(addr + 1)
            hi = memory.read(addr + 2)
            operand = f"(${(hi<<8|lo):04X})"
            size = 3

        elif mode == 6: # ind,B
            lo = memory.read(addr + 1)
            hi = memory.read(addr + 2)
            operand = f"(${(hi<<8|lo):04X}),B"
            size = 3

        elif mode == 7:
            operand = "[DC+B]"
            size = 1

    ### FLOW
    elif cc == 2:
        base = FLOW_NAMES[aaa]
        cond = COND_NAMES[bbb]
        mnemonic = base + " " + cond

        # BRA/BSR relativo
        if aaa in (2, 3):
            offset = memory.read(addr + 1)
            if offset & 0x80:
                offset -= 0x100

            target = (addr + 2 + offset) & 0xFFFF
            operand = f"${target:04X}"
            size = 2

        elif aaa == 4:  # RET
            size = 1
            
        else:
            # JMP/JSR absoluto
            lo = memory.read(addr + 1)
            hi = memory.read(addr + 2)
            operand = f"${(hi<<8|lo):04X}"
            size = 3

    ### SPECIAL
    elif cc == 3:
        #mnemonic = SPECIAL_NAMES[aaa]

        if aaa == 0: # MOV
            mnemonic = "MOV" + " " + REG_REG_NAMES[bbb]
            size = 1

# INC (aaa=1) y DEC (aaa=3) usan tabla REG_NAMES para decodificar bbb.

        elif aaa == 1: # INC
            mnemonic = "INC" + " " + REG_NAMES[bbb]
            size = 1
        
        elif aaa == 2: # DEC
            mnemonic = "DEC" + " " + REG_NAMES[bbb]
            size = 1
        
        elif aaa == 3: # Shifts y Rotates
            operand = SHIFT_NAMES[bbb]
            size = 1

        elif aaa == 4: # NEG/CLR
            if bbb <= 3:
                mnemonic = "NEG" + " " + REG_NAMES[bbb]
            elif bbb <= 7:
                mnemonic = "CLR" + " " + REG_NAMES[bbb-4]
            size = 1

        elif aaa == 5: # Flags
            if bbb == 0:
                mnemonic = "CLC"
            elif bbb == 1:
                mnemonic = "SEC"
            elif bbb == 2:
                mnemonic = "CLV"
            elif bbb == 4:
                mnemonic = "CLI"
            elif bbb == 5:
                mnemonic = "SEI"
            size = 1

        elif aaa == 6:
            mnemonic = STACK_NAMES[bbb]
            size = 1

        elif aaa == 7: # System
            if bbb == 0:
                mnemonic = "NOP"
            elif bbb == 1:
                mnemonic = "BRK"
            elif bbb == 2:
                mnemonic = "HLT"
            size = 1

    ### BYTES STRING
    if size == 1:
        bytes_str = f"{op:02X}"
    elif size == 2:
        bytes_str = f"{op:02X} {memory.read(addr+1):02X}"
    else:
        bytes_str = f"{op:02X} {memory.read(addr+1):02X} {memory.read(addr+2):02X}"

    return f"{addr:04X}: {bytes_str:<8} {mnemonic} {operand}", size


def disassemble(cpu):
    line, size = disassemble_at(cpu.memory, cpu.PC)
    return line
