;;; Tests framebuffer and interruptions, drawing pixels

; Main code/program is in 0x0000, PC starts here at reset
.org $0000
    CLI       ; clear interrupt flag to accept IRQs
    LDA #$DD  ; initialize registers
    LDB #$BB
    CLR C
    LDD #$A0

; Simple loop running while receiving IRQs from an external timer at 60hz.
LOOP:
    CPC #$FF    ; C starts in 0 and is incremented in the IRQ subroutine
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
    STA $0100 ; saves low nibble
    SHL A     ; shift low nibble to high nibble
    SHL A
    SHL A
    SHL A
    ORA $0100 ; restores low nibble
    RET

; IRQ vector address
.org $FFFC
    .word IRQ
