### CPU Emulator Assembler
### v1.0

# Tablas base
REGISTERS = {
    "A": 0,
    "B": 1,
    "C": 2,
    "D": 3,
    "[DC]": 4
}

CONDITIONS = {
    "UN": 0,
    "ZF": 1,
    "NZ": 2,
    "NF": 3,
    "NN": 4,
    "CF": 5,
    "NC": 6,
    "VF": 7
}

ALU_OPS = {
    "ADC": 0,
    "SBB": 1,
    "AND": 2,
    "ORA": 3,
    "XOR": 4,
    "CMP": 5,
    "CPB": 6,
    "CPC": 7
}

LOAD_OPS = {
    "LDA": 0,
    "LDB": 1,
    "LDC": 2,
    "LDD": 3,
    "STA": 4,
    "STB": 5,
    "STC": 6,
    "STD": 7
}

REG_REG = {
    "A,B": 0,
    "A,C": 1,
    "A,D": 2,
    "B,A": 3,
    "C,A": 4,
    "D,A": 5,
    "B,C": 6,
    "C,B": 7
    }

FLOW_OPS = {
    "JMP": 0,
    "JSR": 1,
    "BRA": 2,
    "BSR": 3,
    "RET": 4,
    "RTI": 5
}

SPECIAL_OPS = {
    "MOV": 0,
    "INC": 1,
    "DEC": 2,
    "SHL": 30,
    "SHR": 31,
    "ROL": 32,
    "ROR": 33,
    "NEG": 40,
    "CLR": 41,
    "CLC": 50,
    "SEC": 51,
    "CLV": 52,
    "CLI": 54,
    "SEI": 55,
    "PSH": 60,
    "PLL": 61,
    "NOP": 70,
    "BRK": 71,
    "HLT": 72
}

STACK_OPS = {
    "A": 0,
    "B": 1,
    "DC": 2,
    "FL": 3
}    

### Helpers
def build_opcode(aaa, bbb, cc):
    return (aaa << 5) | (bbb << 2) | cc

def parse_number(text):
    text = text.strip()

    if text.startswith("$"):
        return int(text[1:], 16)
    
    if text.startswith("%"):
        return int(text[1:], 2)

    return int(text)

def clean_line(line):
    # elimina comentarios
    if ";" in line:
        line = line[:line.index(";")]
    return line.strip()

def split_instruction(line):
    parts = line.split()

    if len(parts) == 1:
        return parts[0].upper(), None

    instr = parts[0].upper()
    operand = line[len(parts[0]):].strip()

    return instr, operand


### CLASE ASSEMBLER
class Assembler:

    def __init__(self):
        self.labels = {}
        self.segments = []          # lista de (addr, data)
        self.current_segment = None
        self.pc = 0

    # Segmentos, para escribir en dstintas direcciones de memoria
    def start_segment(self, addr):
        self.current_segment = bytearray()
        self.segments.append((addr, self.current_segment))
        self.pc = addr

    def resolve_value(self, text):
        text = text.strip().upper()

        if "+" in text or "-" in text:
            if "+" in text:
                base, offset = text.split("+")
                sign = 1
            else:
                base, offset = text.split("-")
                sign = -1

            base = base.strip()
            offset = offset.strip()

            if base in self.labels and offset.isdigit():
                return self.labels[base] + sign * int(offset)

        if text in self.labels:
            return self.labels[text]

        return parse_number(text)

    # Funcion para identificar el tipo de direccionamiento
    def detect_addressing(self, op):

        op = op.strip().upper()

        # inmediato
        if op.startswith("#"):
            val = self.resolve_value(op[1:]) # inmediato para LOAD, STORE y ALU en A
            return 0, val, 1

        # [DC] o [DC+B]
        elif op.startswith("[DC"):
            if "[DC+B]" in op:
                return 7, None, 0
            return 4, None, 0

        # (xxxx) o (xxxx)+B donde xxxx puede ser tambien un label
        elif op.startswith("("):
            inner = op[1:op.index(")")].strip().upper()
            val = self.resolve_value(inner)
            if ")+B" in op:
                return 6, val, 2
            return 5, val, 2

        elif "+" in op and not op.startswith("("):
            # abs+B o abs+C
            base, idx = op.split("+")      # Parte el operando en 2 por el signo +
            idx = idx.strip().upper()
            val = self.resolve_value(base.strip())
            if idx == "B":
                return 2, val, 2
            if idx == "C":
                return 3, val, 2

        else:
            try: # Absoluto, fallback general
                val = self.resolve_value(op)
                return 1, val, 2
            except: # si falla el resolve value
                raise Exception(f"{op}: operando inválido")


    # PRIMERA PASADA
    def first_pass(self, lines):
        # first_pass solo calcula tamaños y labels, usa el contador PC como temporal
        pc = 0x0100 #inicio por default, si hay directiva .org se sobreescribe

        for line in lines:
            line = clean_line(line)
            if not line:
                continue

            if line.startswith("."):
                parts = line.split()
                directive = parts[0]
                if directive == ".org":
                    pc = parse_number(parts[1])
                    continue
                if directive == ".byte":
                    values = parts[1].split(",")
                    pc += len(values)
                    continue
                if directive == ".word":
                    values = parts[1].split(",")
                    pc += 2 * len(values)
                    continue

            # identifica labels
            if line.endswith(":"):
                label = line[:-1]
                self.labels[label.strip().upper()] = pc 
                continue

            instr, operand = split_instruction(line)

            size = 1 # Opcode ocupa 1 byte

            if operand:
                if instr.startswith("BRA") or instr.startswith("BSR"):
                    size += 1  # offset relativo (1 byte)

                elif operand.startswith("#"):
                    size += 1  # inmediato

                elif instr in SPECIAL_OPS:
                    size += 0  # Tienen operando pero ocupan solo 1 byte
                    
                elif operand.startswith("[DC"):
                    size += 0  # implícito

                else:
                    size += 2  # absoluto (2 bytes)

            pc += size

    # SEGUNDA PASADA
    def second_pass(self, lines):

        for line in lines:
            line = clean_line(line)
            if not line:
                continue

            if line.startswith("."):
                parts = line.split()
                directive = parts[0]
                if directive == ".org":              # Si se usa .byte o .word, siempre usar .org antes, sino graba en 0x0100 por default
                    addr = parse_number(parts[1])
                    self.start_segment(addr)
                    continue
                if directive == ".byte":             # .byte no soporta labels
                    values = parts[1].split(",")
                    for v in values:
                        self.emit(parse_number(v))
                    continue
                if directive == ".word":             # .word soporta labels
                    values = parts[1].split(",")
                    for v in values:
                        if v.strip().upper() in self.labels:
                            val = self.labels[v.strip().upper()]
                        else:
                            val = parse_number(v)
                        self.emit(val & 0xFF)
                        self.emit((val >> 8) & 0xFF)
                    continue

            if line.endswith(":"):
                continue

            instr, operand = split_instruction(line)
            self.assemble_instruction(instr, operand)

    ### ENSAMBLAR
    def assemble_instruction(self, instr, operand):

        # ALU
        if instr in ALU_OPS:            
            aaa = ALU_OPS[instr]
            bbb, value, size = self.detect_addressing(operand)
                    
            opcode = build_opcode(aaa, bbb, 0)
            self.emit(opcode)
            
            if value is not None:
                self.emit_word(value, size)
            
            return

        # LOAD
        if instr in LOAD_OPS:
            if instr in ["STA", "STB", "STC", "STD"] and operand.startswith("#"):
                raise Exception(f"{instr} no soporta modo inmediato")

            aaa = LOAD_OPS[instr]
            bbb, value, size = self.detect_addressing(operand)

            opcode = build_opcode(aaa, bbb, 1)
            self.emit(opcode)

            if value is not None:
                self.emit_word(value, size)

            return

        # FLOW
        if instr in FLOW_OPS:
            aaa = FLOW_OPS[instr]
            if operand and aaa < 4:
                # caso: "label" (incondicional)
                if "," not in operand:
                    bbb = 0  # UN
                    idx = operand.strip().upper()

                else:
                    # caso: "ZF,label"
                    cond, target = operand.split(",")
                    cond = cond.strip().upper()
                    idx = target.strip().upper()

                    bbb = CONDITIONS[cond]

                opcode = build_opcode(aaa, bbb, 2)
                self.emit(opcode)

                # resolver destino
                if idx in self.labels:
                    target = self.labels[idx]
                else:
                    target = parse_number(idx)

                # BRA / BSR RELATIVO (1 byte)
                if instr in ["BRA", "BSR"]:
                    offset = target - (self.pc + 1)

                    if offset < -128 or offset > 127:
                        raise Exception("Branch fuera de rango")

                    self.emit(offset & 0xFF)

                # RESTO ABSOLUTO (2 bytes)
                else:
                    self.emit_word(target, 2)
                return
                
            elif aaa == 4 or aaa == 5:  # RET/RTI, no llevan operando
                opcode = build_opcode(aaa, 0, 2)
                self.emit(opcode)
                return           
             
            else:
                raise Exception(f"{instr} no soporta ese modo")

        # SPECIAL
        if instr in SPECIAL_OPS:
            aaa = SPECIAL_OPS[instr]
            bbb = 0

            if operand:
                operand = operand.strip().upper()

            if aaa == 0: # MOV
                if operand in REG_REG:
                    bbb = REG_REG[operand]

            elif aaa == 1 or aaa == 2:   # INC/DEC
                if operand in REGISTERS:
                    bbb = REGISTERS[operand]            

            #Shifts y rotates
            elif 30 <= aaa <= 33:
                # Registro para shifts y rotates de SPECIAL
                if operand in ["A", "B"]:
                    if operand == "A":
                        base = 0
                    if operand == "B":
                        base = 4
                bbb = base + (aaa - 30)
                aaa = 3

            elif aaa == 40: # NEG
                if operand in REGISTERS:
                    bbb = REGISTERS[operand]
                    aaa = 4
            elif aaa == 41: # CLR
                if operand in REGISTERS:
                    bbb = REGISTERS[operand] + 4
                    aaa = 4

            # CLC, SEC, CLV, CLI, SEI
            elif 50 <= aaa <= 55:
                bbb = aaa % 10
                aaa = 5

            elif aaa == 70: # NOP
                aaa = 7
                bbb = 0
            elif aaa == 72: # HLT
                aaa = 7
                bbb = 2

            #PUSH/PULL
            elif aaa == 60:
                bbb = STACK_OPS[operand]
                aaa = 6
               
            elif aaa == 61:
                bbb = STACK_OPS[operand] + 4
                aaa = 6

            opcode = build_opcode(aaa, bbb, 3)
            self.emit(opcode)

            return

        raise Exception("Instrucción desconocida: " + instr)

    # EMITIR BYTES
    def emit(self, byte):
        if self.current_segment is None:
            self.start_segment(0x0100) # Si no hay segmentos creados con .org, carga en 0x100 por defecto
        self.current_segment.append(byte & 0xFF)
        self.pc += 1

    def emit_word(self, value, size):
        if size == 1:
            self.emit(value)
        else:
            self.emit(value & 0xFF)
            self.emit((value >> 8) & 0xFF)


# FUNCIÓN PRINCIPAL
def assemble(code):
    asm = Assembler()
    lines = code.splitlines()

    asm.first_pass(lines)
    asm.second_pass(lines)

    return asm.segments


