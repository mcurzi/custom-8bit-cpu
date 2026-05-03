;;; Test Load/Store/Move
ldb #$20
stb $03
stb $B3
ldc #$02
stc $03+b
lda #$10
sta $20
ldb ($03)
lda #$A0
ldd #$02
sta [DC]
sta ($03)+b
mov a,b
mov a,c
ldb #$BB
mov b,c
mov b,a
ldc $03
mov c,a
mov c,b
mov a,d
ldd $30
std [DC+B]
mov d,a
hlt
