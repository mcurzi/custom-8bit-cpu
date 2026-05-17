;;; Animated Pacman ghost example

.org $0200
; 2 sprites, 16x16 px (16x8 bytes) each
.byte $00,$00,$00,$BB,$BB,$00,$00,$00
.byte $00,$00,$BB,$BB,$BB,$BB,$00,$00
.byte $00,$0B,$BB,$BB,$BB,$BB,$B0,$00
.byte $00,$BB,$BF,$FB,$BB,$BF,$F0,$00
.byte $00,$BB,$FF,$FF,$BB,$FF,$FF,$00
.byte $00,$BB,$FF,$99,$BB,$FF,$99,$00
.byte $0B,$BB,$FF,$99,$BB,$FF,$99,$B0
.byte $0B,$BB,$BF,$FB,$BB,$BF,$FB,$B0
.byte $0B,$BB,$BB,$BB,$BB,$BB,$BB,$B0
.byte $0B,$BB,$BB,$BB,$BB,$BB,$BB,$B0
.byte $0B,$BB,$BB,$BB,$BB,$BB,$BB,$B0
.byte $0B,$BB,$BB,$BB,$BB,$BB,$BB,$B0
.byte $0B,$BB,$BB,$BB,$BB,$BB,$BB,$B0
.byte $0B,$B0,$BB,$B0,$0B,$BB,$0B,$B0
.byte $0B,$00,$0B,$B0,$0B,$B0,$00,$B0
.byte $00,$00,$00,$00,$00,$00,$00,$00

.byte $00,$00,$00,$BB,$BB,$00,$00,$00
.byte $00,$00,$BB,$BB,$BB,$BB,$00,$00
.byte $00,$0B,$BB,$BB,$BB,$BB,$B0,$00
.byte $00,$BB,$BF,$FB,$BB,$BF,$F0,$00
.byte $00,$BB,$FF,$FF,$BB,$FF,$FF,$00
.byte $00,$BB,$FF,$99,$BB,$FF,$99,$00
.byte $0B,$BB,$FF,$99,$BB,$FF,$99,$B0
.byte $0B,$BB,$BF,$FB,$BB,$BF,$FB,$B0
.byte $0B,$BB,$BB,$BB,$BB,$BB,$BB,$B0
.byte $0B,$BB,$BB,$BB,$BB,$BB,$BB,$B0
.byte $0B,$BB,$BB,$BB,$BB,$BB,$BB,$B0
.byte $0B,$BB,$BB,$BB,$BB,$BB,$BB,$B0
.byte $0B,$BB,$BB,$BB,$BB,$BB,$BB,$B0
.byte $0B,$BB,$B0,$BB,$BB,$0B,$BB,$B0
.byte $00,$BB,$00,$0B,$B0,$00,$BB,$00
.byte $00,$00,$00,$00,$00,$00,$00,$00

.org $0100
fb_ptr:
    .word $8AB8    ; initial location in framebuffer

spr_ptr:
    .word $0200

.org $0000

start:
    CLI
    CLR A
    STA $1000       ; last low bite FB
    STA $1001       ; movement direction
    STA $1002       ; interrupt counter
    LDA #$03        ; animation speed (60hz/A)
    STA $1003       ; guarda velocidad en RAM

; Empty main loop, just to capture timer interruptions
loop:
    BRA loop

irq:
    ; interrupt counter
    LDB $1002
    INC B
    STB $1002
    CPB $1003
    JMP zf,run_movement
    JMP un,skip


run_movement:
    CLR B      ; offset
    CLR C      ; sprite width counter
    LDA fb_ptr
    STA $1000
copy_loop:
    LDA (spr_ptr)+B    ; read sprite
    PSH B      ; push B to stack
    MOV c,b
    PSH dc
    LDC $1001
    CPC #$00
    JSR nz, flip_nibbles
    PLL dc
    STA (fb_ptr)+B    ; write in FB with offset B

    ; the following 5 lines insert a black byte at each side of each
    ; sprite line, to erase trails
    LDA #$00
    LDB #$FF
    STA (fb_ptr)+B
    LDB #$08
    STA (fb_ptr)+B

    PLL B      ; recover B from stack
    INC B
    INC C
    CPC #$08    ; #$08 is the sprite width in bytes
    BRA NZ,copy_loop
    CPB #$80    ; #$80 is the last byte of the sprite
    JMP ZF,cont
    LDC fb_ptr
    MOV C,A
    CLC
    ADC #$80       ; adds $80 to the low byte of fb_ptr to jump to next line
    STA fb_ptr
    PSH B
    LDB #$01
    LDC fb_ptr+B   ; temporary use of B = 1
    BSR CF, INC_hb ; if carry, increases hight byte
    PLL B          ; recover original B
    CLR C
    BRA un,copy_loop

INC_hb:
    INC C
    STC fb_ptr+B
    RET

flip_nibbles: ; horizontal flip when the movement is to the left
    PSH a
    MOV B,A
    xor #%111  ; essentially: A = 7-A
    MOV A,B
    PLL a

    LDD #0
    MOV a,d        ; stores originl byte in D
    AND #$F0       ; keeps high nibble
    SHR A          ; righ displacement to the low nibble
    SHR A
    SHR A
    SHR A
    STA $1005
    ; moves low nibble in D to the high nibble in A
    MOV d,a
    SHL A
    SHL A
    SHL A
    SHL A
    ORA $1005     ; combines both nibbles (flipped) in A
    RET

cont:
    ; change the sprite pointer to the second sprite
    LDA spr_ptr
    CLC
    ADC #$80
    STA spr_ptr

    ; INCreases FB adress for movement
    LDA $1000  ; FB low byte
    ORA #$80
    LDC $1001
    cpc #$00
    JMP zf,move_right
    JMP nz,move_left

move_right:
    LDD #$00
    STD $1001
    INC a
    CMP #$48
    BSR nf,change_d
    JMP end

change_d:
    LDD #$01
    STD $1001
    RET

move_left:
    DEC a
    CMP #$30
    BSR nn,change_d2
    JMP end

change_d2:
    LDD #$00
    STD $1001
    RET

end:
    STA fb_ptr
    LDA #$8A
    LDB #$01
    STA fb_ptr+B ; restores FB high byte
    CLR A
    STA $1002 ; clears interrupt counter

skip:
    RTI

; IRQ vector address
.org $FFFC
    .word irq

