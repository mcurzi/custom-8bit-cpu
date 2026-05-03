;;; Tests IRQs by drawing pixels at 60hz (timer frequency can be changed in main.py)

; Main code chunk is in 0x0100, this is where PC starts
.org $0100
    CLI       ; clear interrupt flag to accept IRQs
    CLR B     ; clear/initialize registers
    CLR C
    LDD #$C0

; Empty loop, just running CPU while receiving
; interruptions from an external timer at 60hz.
LOOP:
    BRA LOOP

; IRQ subroutine
.org $0200
IRQ:
    LDA #$90
    STA $9000+C
    LDA #$60
    STA $A000+C
    STB $B000+C
    STB [DC+B]   ; DC pointer, indexed with B
    INC C
    INC B
    RTI

; IRQ vector address
.org $FFFC
    .word IRQ
