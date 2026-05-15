### CPU Emulator Assembler v1.0

INSTRUCTION_TABLE = {
    # ALU (cc=0)
    "ADC": (0, 0, 0), "SBB": (1, 0, 0), "AND": (2, 0, 0), "ORA": (3, 0, 0),
    "XOR": (4, 0, 0), "CMP": (5, 0, 0), "CPB": (6, 0, 0), "CPC": (7, 0, 0),
    
    # LOAD/STORE (cc=1)
    "LDA": (0, 0, 1), "LDB": (1, 0, 1), "LDC": (2, 0, 1), "LDD": (3, 0, 1),
    "STA": (4, 0, 1), "STB": (5, 0, 1), "STC": (6, 0, 1), "STD": (7, 0, 1),

    # FLOW (cc=2)
    "JMP": (0, 0, 2), "JSR": (1, 0, 2), "BRA": (2, 0, 2), "BSR": (3, 0, 2),
    "RET": (4, 0, 2), "RTI": (5, 0, 2),

    # SPECIAL (cc=3)
    "MOV": (0, 0, 3), "INC": (1, 0, 3), "DEC": (2, 0, 3),
    "SHL": (3, 0, 3), "SHR": (3, 1, 3), "ROL": (3, 2, 3), "ROR": (3, 3, 3),
    "NEG": (4, 0, 3), "CLR": (4, 4, 3),
    "CLC": (5, 0, 3), "SEC": (5, 1, 3), "CLV": (5, 2, 3), "CLI": (5, 4, 3), "SEI": (5, 5, 3),
    "PSH": (6, 0, 3), "PLL": (6, 4, 3),
    "NOP": (7, 0, 3), "LSP": (7, 1, 3), "HLT": (7, 2, 3)
}

# Tablas base
REGISTERS = {"A": 0, "B": 1, "C": 2, "D": 3, "[DC]": 4}
CONDITIONS = {"UN": 0, "ZF": 1, "NZ": 2, "NF": 3, "NN": 4, "CF": 5, "NC": 6, "VF": 7}
REG_REG = {"A,B": 0, "A,C": 1, "A,D": 2, "B,A": 3, "C,A": 4, "D,A": 5, "B,C": 6, "C,B": 7 } 
STACK_OPS = {"A": 0, "B": 1, "DC": 2, "FL": 3}      

### Helpers
def parse_number(text):
    text = text.strip()
    if text.startswith("$"): return int(text[1:], 16)
    if text.startswith("%"): return int(text[1:], 2)
    return int(text)

def clean_line(line):
    # elimina comentarios
    if ";" in line: line = line[:line.index(";")]
    return line.strip()

def split_instruction(line):
    parts = line.split()
    if len(parts) == 1: return parts[0].upper(), None
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
            op = op.strip().upper().replace(" ", "")

            if op.startswith("#"):          # inmediato
                val = self.resolve_value(op[1:])
                return 0, val, 1

            elif op.startswith("[DC"):           # [DC] o [DC+B]
                if "+B" in op.replace(" ", ""):  # Usa "in" por si hay espacios como "[DC + B]"
                    return 7, None, 0
                return 4, None, 0

            elif op.startswith("("):              # (xxxx) o (xxxx)+B donde xxxx puede ser tambien un label
                inner = op[op.find("(")+1 : op.find(")")].strip()
                val = self.resolve_value(inner)
                if ")+B" in op.replace(" ", ""):
                    return 6, val, 2
                return 5, val, 2

            elif "+" in op:  # abs+B o abs+C
                parts = op.split("+")   # Parte el operando en 2 por el signo +
                base = parts[0].strip()
                idx = parts[1].strip().upper()
                val = self.resolve_value(base)
                if idx == "B": return 2, val, 2
                if idx == "C": return 3, val, 2
                # Si hay un + pero no es B ni C, cae al fallback absoluto por si es un Label+Offset
                return 1, self.resolve_value(op), 2

            else:
                try: # Absoluto, label o direccion
                    val = self.resolve_value(op)
                    return 1, val, 2
                except: # si falla el resolve value
                    raise Exception(f"{op}: operando inválido")

    # PRIMERA PASADA
    def first_pass(self, lines):
        # first_pass solo calcula tamaños y labels, usa el contador PC como temporal
        pc = 0x0000 #inicio por default, si hay directiva .org se sobreescribe

        for line in lines:
            line = clean_line(line)
            if not line:
                continue

            if line.startswith("."):
                parts = line.split(maxsplit=1)  # solo divide en directiva y resto
                directive = parts[0]
                parts[1] = parts[1].replace(" ", "")
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
                if instr.startswith("BRA") or instr.startswith("BSR"): size += 1  # offset relativo (1 byte)
                elif operand.startswith("#"): size += 1  # inmediato
                elif INSTRUCTION_TABLE.get(instr, (0,0,0))[2] == 3: # Si cc es 3 (SPECIAL)
                    if instr == "LSP": size += 2
                    else: size += 0    
                elif operand.startswith("[DC"): size += 0  # implícito
                else: size += 2  # absoluto (2 bytes)
            pc += size

    # SEGUNDA PASADA
    def second_pass(self, lines):
        for line in lines:
            line = clean_line(line)
            if not line or line.endswith(":"): continue

            if line.startswith("."):
                parts = line.split(maxsplit=1)
                directive = parts[0]
                parts[1] = parts[1].replace(" ", "")
                if directive == ".org":              # Si se usa .byte o .word, siempre usar .org antes, sino graba en 0x0000 por default
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

            instr, operand = split_instruction(line)
            self.assemble_instruction(instr, operand)

    ### ENSAMBLAR
    def assemble_instruction(self, instr, operand):
        if instr not in INSTRUCTION_TABLE:
            raise Exception(f"Instrucción desconocida: {instr}")

        aaa, bbb_base, cc = INSTRUCTION_TABLE[instr]
        bbb = bbb_base
        value = None
        size = 0

        # Lógica de operandos según la categoría (cc)
        if cc == 0 or cc == 1:  # ALU y LOAD
            if cc == 1 and instr.startswith("ST") and operand.startswith("#"):
                raise Exception(f"{instr} no soporta modo inmediato")
            bbb, value, size = self.detect_addressing(operand)

        elif cc == 2:  # FLOW
            if operand and aaa < 4:
                cond_str, target_str = (operand.split(",") if "," in operand else ("UN", operand))
                bbb = CONDITIONS[cond_str.strip().upper()]
                target = self.resolve_value(target_str.strip())
                if instr in ["BRA", "BSR"]: # Branches
                    value = target - (self.pc + 2)      # relative distance to the PC + 2 (instr + 1byte operand)
                    if value < -128 or value > 127:
                        raise Exception("Branch fuera de rango")
                    else:
                        value = value & 0xFF
                        size = 1
                else:
                    value = target
                    size = 2

        elif cc == 3:  # SPECIAL
            if operand:
                op_up = operand.strip().upper()
                if instr == "MOV":
                    bbb = REG_REG[op_up]
                elif instr in ["INC", "DEC", "NEG", "CLR"]:
                    bbb = bbb_base + REGISTERS[op_up]
                elif instr in ["SHL", "SHR", "ROL", "ROR"]:
                    reg_offset = 0 if op_up == "A" else 4
                    bbb = reg_offset + bbb_base
                elif instr in ["PSH", "PLL"]:
                    bbb = bbb_base + STACK_OPS[op_up]
                elif instr == "LSP":
                    value = self.resolve_value(operand[1:])
                    size = 2

        # Emisión final unificada
        opcode = (aaa << 5) | (bbb << 2) | cc
        self.emit(opcode)
        if value is not None: self.emit_word(value, size)
        
    # EMITIR BYTES
    def emit(self, byte):
        if self.current_segment is None:
            self.start_segment(0x0000) # Si no hay segmentos creados con .org, carga en 0x0000 por defecto
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
