;;; Test program flow: JMP/BSR/JSR/RET
LDA #$FB

loop:
ADC #$02
BSR CF,incrB  ; Branch if carry to incrB ($0112). No need to compare, CF will be 1 if A > #$FF
JMP ZF,cont   ; jump if zero to $010C
JMP loop      ; unconditional jump to $0102
cont:
JSR decrC     ; unconditional jsr to decrC ($0117)
JMP end       ; unconditional jsr to end ($0119)

incrB:
INC b
CLC
SBB #$01      ; this substract activates ZF
RET

decrC:
DEC C
RET

end:
HLT
