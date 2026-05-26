### CPU Emulator Assembler v1.0

# Opcode and operand tables
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

REGISTERS = {"A": 0, "B": 1, "C": 2, "D": 3, "[DC]": 4}
CONDITIONS = {"UN": 0, "ZF": 1, "NZ": 2, "NF": 3, "NN": 4, "CF": 5, "NC": 6, "VF": 7}
REG_REG = {"A,B": 0, "A,C": 1, "A,D": 2, "B,A": 3, "C,A": 4, "D,A": 5, "B,C": 6, "C,B": 7 } 
STACK_OPS = {"A": 0, "B": 1, "DC": 2, "FL": 3}      

# Helpers
def parse_number(text):
    text = text.strip()
    if text.startswith("$"): return int(text[1:], 16)
    if text.startswith("%"): return int(text[1:], 2)
    return int(text)

def clean_line(line):      # removes comments
    if ";" in line: line = line[:line.index(";")]
    return line.strip()

def split_instruction(line):
    parts = line.split()
    if len(parts) == 1: return parts[0].upper(), None
    instr = parts[0].upper()
    operand = line[len(parts[0]):].strip()
    return instr, operand

### Assembler Class
class Assembler:

    def __init__(self):
        self.labels = {}
        self.segments = []          # list of tuples (address, compiled code)
        self.current_segment = None
        self.pc = 0

    # Segments are used to write in different parts of the memory using the .org directive
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

    # Method to identify addressing mode
    def detect_addressing(self, op):
            op = op.strip().upper().replace(" ", "")

            if op.startswith("#"):          # immediate
                val = self.resolve_value(op[1:])
                return 0, val, 1

            elif op.startswith("[DC"):           # [DC] or [DC+B]
                if "+B" in op.replace(" ", ""):  # Ignores spaces, as in "[DC + B]"
                    return 7, None, 0
                return 4, None, 0

            elif op.startswith("("):              # (xxxx) o (xxxx)+B where xxxx can also be a label
                inner = op[op.find("(")+1 : op.find(")")].strip()
                val = self.resolve_value(inner)
                if ")+B" in op.replace(" ", ""):
                    return 6, val, 2
                return 5, val, 2

            elif "+" in op:  # abs+B o abs+C
                parts = op.split("+")   # Splits the operand in 2 at the + sign
                base = parts[0].strip()
                idx = parts[1].strip().upper()
                val = self.resolve_value(base)
                if idx == "B": return 2, val, 2
                if idx == "C": return 3, val, 2
                # If there is a + but not B or C, goes to the absolute fallback (can be an integer offset)
                return 1, self.resolve_value(op), 2

            else:
                try: # Absolute, label or address
                    val = self.resolve_value(op)
                    return 1, val, 2
                except: # if resolve_value fails
                    raise Exception(f"{op}: invalid operand")

    ## First pass
    def first_pass(self, lines):
        # first_pass only calculates size y labels, uses PC as temporal
        pc = 0x0000 # start by default, if there are .org directives, pc will change

        for line in lines:
            line = clean_line(line)
            if not line:
                continue

            if line.startswith("."):
                parts = line.split(maxsplit=1)  # only splits directive from rest
                directive = parts[0]
                parts[1] = parts[1].replace(" ", "")
                if directive == ".org":
                    pc = parse_number(parts[1])  # here, part[1] is a memory address
                    continue
                if directive == ".byte":
                    values = parts[1].split(",")
                    pc += len(values)
                    continue
                if directive == ".word":
                    values = parts[1].split(",")
                    pc += 2 * len(values)
                    continue

            # Identifies labels
            if line.endswith(":"):
                label = line[:-1]
                self.labels[label.strip().upper()] = pc 
                continue

            instr, operand = split_instruction(line)
            size = 1 # Opcode size is always 1 byte

            if operand:
                if instr.startswith("BRA") or instr.startswith("BSR"): size += 1  # relative offset (1 byte)
                elif operand.startswith("#"): size += 1  # inmediato
                elif INSTRUCTION_TABLE.get(instr, (0,0,0))[2] == 3: # If cc is 3 (SPECIAL)
                    if instr == "LSP": size += 2
                    else: size += 0    
                elif operand.startswith("[DC"): size += 0  # implicit
                else: size += 2  # absolute (2 bytes)
            pc += size

    ## Second pass
    def second_pass(self, lines):
        for line in lines:
            line = clean_line(line)
            if not line or line.endswith(":"): continue

            if line.startswith("."):
                parts = line.split(maxsplit=1)
                directive = parts[0]
                parts[1] = parts[1].replace(" ", "")
                if directive == ".org":              # If using .byte o .word, always use .org $addr first
                    addr = parse_number(parts[1])
                    self.start_segment(addr)         # This creates a new code segment
                    continue
                if directive == ".byte":             # .byte does not support labels
                    values = parts[1].split(",")
                    for v in values:
                        self.emit(parse_number(v))
                    continue
                if directive == ".word":             # .word supports labels
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

    ## Assemble instrucion method
    def assemble_instruction(self, instr, operand):
        if instr not in INSTRUCTION_TABLE:
            raise Exception(f"Unknown instruction: {instr}")

        aaa, bbb_base, cc = INSTRUCTION_TABLE[instr]
        bbb = bbb_base
        value = None
        size = 0

        # Operand logic by group (cc)
        if cc == 0 or cc == 1:  # ALU and LOAD
            if cc == 1 and instr.startswith("ST") and operand.startswith("#"):
                raise Exception(f"{instr} does nor support immediate mode")
            bbb, value, size = self.detect_addressing(operand)

        elif cc == 2:  # FLOW
            if operand and aaa < 4:
                cond_str, target_str = (operand.split(",") if "," in operand else ("UN", operand))
                bbb = CONDITIONS[cond_str.strip().upper()]
                target = self.resolve_value(target_str.strip())
                if instr in ["BRA", "BSR"]: # Branches
                    value = target - (self.pc + 2)      # relative distance to the PC + 2 (instr + 1 byte operand)
                    if value < -128 or value > 127:
                        raise Exception("Branch out of range")
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

        # Assembled insrtucion (opcode + operand) emision.
        opcode = (aaa << 5) | (bbb << 2) | cc
        self.emit(opcode)
        if value is not None: self.emit_word(value, size)
        
    # Writes bytes of assembled code 
    def emit(self, byte):
        if self.current_segment is None:
            self.start_segment(0x0000) # If there are no segments created with .org, loads program in 0x0000 by default
        self.current_segment.append(byte & 0xFF)
        self.pc += 1

    # Writes either bytes or words (2 bytes) of code, used for operands.
    def emit_word(self, value, size):
        if size == 1:
            self.emit(value)
        else:
            self.emit(value & 0xFF)
            self.emit((value >> 8) & 0xFF)
            
## Main function
def assemble(code):
    asm = Assembler()
    lines = code.splitlines()

    asm.first_pass(lines)
    asm.second_pass(lines)

    return asm.segments
