;;; Tests framebuffer and IRQs by drawing pixels at 60hz

; Main code/program is in 0x0000, this is where PC starts
.org $0000
    CLI       ; clear interrupt flag to accept IRQs
    LDA #$DD  ; initialize registers
    LDB #$BB
    CLR C
    LDD #$A0

; Empty loop, just running CPU while receiving
; interruptions from an external timer at 60hz.
LOOP:
    CPC #$FF
    BRA NC,end  ; branch if not minus (No Carry flag)
    BRA LOOP

end:
    HLT

; IRQ subroutine
.org $0200
IRQ:
    STA $8000+C
    STB $9000+C
    PSH A
    JSR UN,rep_color
    STA [DC]   ; DC pointer
    INC C
    PLL A
    RTI

rep_color:
    MOV C,A
    AND #$0F
    STA $0100 ; sabes low nibble
    SHL A     ; shift low nibble to high nibble
    SHL A
    SHL A
    SHL A
    ORA $0100 ; restores low nibble
    RET

; IRQ vector address
.org $FFFC
    .word IRQ
