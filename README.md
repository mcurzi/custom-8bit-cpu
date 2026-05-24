# 8-bit CPU Emulator

A fully custom 8-bit CPU architecture designed and implemented from scratch in Python, including:

- Custom ISA & opcode encoding
- Interrupt handling
- Assembler & disassembler
- Memory-mapped graphics
- Real-time debugger GUI
- Examples in assembly code

<p align="center">
  <img src="demo.gif" width="650">
</p>

*Emulated execution at ~2.0 MHz, framebuffer at ~60 fps*

---

## Architecture

### Registers & Flags

| Registers | Description | Flags | Description |
| :--- | :--- | :--- | :--- |
| **A** | Accumulator | **Z** | Zero flag |
| **B, C, D** | General-purpose | **N** | Negative flag |
| **DC** | 16-bit pointer (D:H, C:L) | **CF** | Carry flag |
| **PC / SP** | Program Counter / Stack | **V** | Overflow flag |

### Instruction Format: `AAA BBB CC`
* **AAA**: Operation (3 bits)
* **BBB**: Operand / Mode / Condition (3 bits)
* **CC**: Instruction Group (2 bits: 00=ALU, 01=LOAD/STORE, 10=Flow, 11=Special)

## Instruction Groups

### ALU (CC = 00)
Operations using **A** as accumulator: **ADC, SBB, AND, ORA, XOR, CMP, CPB, CPC**.

### LOAD / STORE (CC = 01)
**Addressing modes:**
* Immediate (`#value`), Absolute (`$ADDR`).
* Indexed (`$ADDR+B`, `$ADDR+C`).
* Indirect (`($ADDR)`) and Indirect Indexed (`($ADDR)+B`).
* Memory via DC pointer (`[DC]`, `[DC+B]`).

### FLOW CONTROL (CC = 10)
* **Instructions:** JMP, JSR, BRA, BSR, RET, RTI.
* **Conditions:** ZF, NZ, NF, NN, CF, NC, VF.

### SPECIAL (CC = 11)
**MOV, INC, DEC, NEG, CLR, PSH, PLL**, shifts/rotations, and flag control (CLC, SEC, etc.).

## Interrupt System
* **IRQ (maskable):** Vector `0xFFFC`. Controlled by I flag.
* **NMI (non-maskable):** Vector `0xFFFA`. Edge-triggered.
* **Mechanism:** Pushes PC (16-bit) and Flags to stack. Return via `RTI` instruction.

## Memory Map

| Range | Function |
| :--- | :--- |
| `$0000 - $5FFF` | General purpose RAM  |
| `$6000 - $BFFF` |  **Graphics Framebuffer** (256x192 px, 2bpp)  |
| `$C000 - $EFFF` | System RAM (stack, I/O, future runtime data) |
| `$F000 - $FFFF` | System area (future boot and system code, vectors) |

---

## Example Program
```assembly
.org $0000
    CLI             ; Enable interrupts
    LDA #$DD
    CLR B

LOOP:
    BRA LOOP        ; Idle loop

IRQ:
    STA $9000+B     ; Write to framebuffer
    INC B
    RTI

.org $FFFC
    .word IRQ       ; IRQ Vector

```

## Project Structure

* `cpu.py`: CPU core & Memory bus.
* `assembler.py`: Two-pass assembler.
* `disassembler.py`: Generates a disassembly of next instruction.
* `timer.py`: Simple timer to generate IRQ/NMI signals.
* `ui.py`: Tkinter dashboard & Framebuffer.
* `main.py`: Application entry point.

---

## Quick Start

1. **Clone the repository**
2. **Run:** `python main.py`
3. **Execution:** Write or paste the program in assembly code in the editor. Compile and load the program with the **Asm/Load**. If the program loaded correctly in memory, use **Run/Pause** or **Step** to execute.


## Project Status

*   **Core:** Complete
*   **Toolchain:** Complete (Assembler/Disassembler)
*   **UI/Visuals:** Complete
*   **Testing:** In progress

## Why this project exists

This project was developed as a personal challenge. It served as a practical exercise to better understand how a CPU works from the foundations, to learn low-level programming and to improve my Python development skills by building a simple but functional emulator from scratch.

## Inspiration

The design draws inspiration from what I have read about classic 8-bit architectures, such as the **MOS 6502**, **Zilog Z80**, and **Intel 8080**. I decided to implement my own instruction set and encoding model for educational purposes, without compromising realism.

