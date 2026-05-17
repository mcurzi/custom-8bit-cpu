;;; Test Load/Store/Move and different adressing modes

ldb #$1F    ; imm
stb $83     ; abs
stb $B3
ldc #$A2
stc $83+b   ; abs+B
lda #$C0
sta $B0
ldb ($83)   ; (ptr) $1F + #$1B
ldd #$02
sta [DC]    ; DC pointer: adress $02A2
sta ($83)+b ; (ptr)+B: $001F + #$1B = $003A
mov a,b
mov a,c
ldb #$BB
mov b,c
mov b,a
ldc $12    ; #$35
mov c,a
mov c,b
mov a,d
ldd $2B    ; #$17
std [DC+B] ; DC pointer + B offset: $1735 + #$35 = $176A
mov d,a
hlt
