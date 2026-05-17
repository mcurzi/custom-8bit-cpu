;;; Test program flow: JMP/BSR/JSR/RET
LDA #$FB

loop:
ADC #$02
BSR CF,incrB  ; Branch if carry to incrB ($0012). CF will be 1 when A > #$FF
JMP ZF,cont   ; jump if zero to $000C
JMP loop      ; unconditional jump to $0002
cont:
JSR decrC     ; unconditional jsr to decrC ($0017)
JMP end       ; unconditional jsr to end ($0019)

incrB:
INC B
CLC
SBB #$01      ; this substract activates ZF
RET

decrC:
DEC C
RET

end:
HLT
