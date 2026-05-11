# 📑 Custom 8-bit ISA Reference

This document provides the official technical specification for the 8-bit CPU architecture. It covers instruction formats, register sets, addressing modes, and flag logic.

## 🏗 General Format
Each instruction has a base size of **1 byte**, plus additional operands where applicable.

**Opcode Structure:** `AAA BBB CC`
*   **AAA**: Operation (bits 7-5)
*   **BBB**: Mode / Sub-op / Register (bits 4-2)
*   **CC**: Instruction Group (bits 1-0)

**Hex Calculation:** `(AAA << 5) | (BBB << 2) | CC`

---

## 🗄 Registers
| Register | Size | Description |
| :--- | :--- | :--- |
| **A** | 8-bit | Accumulator (Main ALU register) |
| **B, C, D** | 8-bit | General Purpose |
| **DC** | 16-bit | Data/Pointer Register (D = High, C = Low) |
| **PC** | 16-bit | Program Counter |
| **SP** | 16-bit | Stack Pointer |

---

## 🛠 Instruction Groups

### Group 00: ALU (Arithmetic Logic Unit)
Operations performed on the **A** accumulator.

**Operations (AAA):**
* `000`: ADC (Add with Carry)
* `001`: SBB (Subtract with Borrow)
* `010`: AND
* `011`: ORA
* `100`: XOR
* `101`: CMP (Compare with A)
* `110`: CPB (Compare with B)
* `111`: CPC (Compare with C)

**Addressing Modes (BBB):**
1. `#imm`: Immediate (1 extra byte)
2. `abs`: Absolute (2 extra bytes)
3. `abs+B`: Absolute indexed by B
4. `abs+C`: Absolute indexed by C
5. `[DC]`: Indirect via DC register (0 extra bytes)
6. `($addr)`: Absolute Indirect (2 extra bytes)
7. `($addr)+B`: Absolute Indirect post-indexed by B
8. `[DC+B]`: Indirect via DC indexed by B

---

### Group 01: LOAD / STORE
Data transfer between registers and memory.

**Operations (AAA):**
* `000-011`: LDA, LDB, LDC, LDD
* `100-111`: STA, STB, STC, STD

**Addressing (BBB):**
* Same modes as the ALU group.
* *Note: Immediate modes are only valid for LOAD operations.*

---

### Group 10: Flow Control
Branching and subroutine instructions.

**Operations (AAA):**
* `000`: JMP (Jump Absolute)
* `001`: JSR (Jump to Subroutine)
* `010`: BRA (Branch Relative - 1 byte signed offset)
* `011`: BSR (Branch to Subroutine Relative)
* `100`: RET (Return from Subroutine)
* `101`: RTI (Return from Interrupt)

**Conditions (BBB):**
`000`: Always | `001`: Z | `010`: NZ | `011`: N | `100`: NN | `101`: C | `110`: NC | `111`: V

---

### Group 11: Register / Bit / Misc
Special operations and register manipulation.

*   **MOV (AAA=000)**: Register-to-register transfer (BBB defines src/dest).
*   **INC/DEC (AAA=001/010)**: Increment/Decrement A, B, C, D, or the 16-bit DC pair.
*   **SHIFT/ROTATE (AAA=011)**: SHL, SHR, ROL, ROR on A or B.
*   **STACK (AAA=110)**: PUSH/PULL for A, B, DC, or Flags.
*   **SYS (AAA=111)**: NOP, LSP, HLT.

---

## 🚩 Status Flags
The CPU maintains 5 status flags:

1.  **Z (Zero)**: Set if the result is 0.
2.  **N (Negative)**: Set if bit 7 of the result is 1.
3.  **C (Carry)**: Set on unsigned overflow (addition) or borrow (subtraction).
4.  **V (Overflow)**: Set on signed arithmetic overflow (two's complement).
5.  **I (Interrupt Disable)**: Disables IRQs when set.

### Flag Behavior by Instruction:
| Instruction | Z | N | C | V |
| :--- | :---: | :---: | :---: | :---: |
| **ADD / SUB** | ✅ | ✅ | ✅ | ✅ |
| **AND/OR/XOR**| ✅ | ✅ | - | - |
| **LDA/LDB/MOV**| ✅ | ✅ | - | - |
| **INC / DEC** | ✅ | ✅ | - | ✅ |
| **CMP** | ✅ | ✅ | ✅ | - |

---

## 💾 Memory Map
| Range | Function |
| :--- | :--- |
| `$0000 - $5FFF` | General purpose RAM  |
| `$6000 - $BFFF` |  **Graphics Framebuffer** (256x192 px, 2bpp)  |
| `$C000 - $EFFF` | System RAM (stack, I/O, future runtime data) |
| `$F000 - $FFFF` | System area (future boot and system code, vectors |

