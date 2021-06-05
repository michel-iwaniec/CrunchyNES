.org $7FF0
.byte "NES",$1A
.byte 2   ; 16 kB PRG banks
.byte 0   ; 32kB switchable CHR RAM
.byte $E3 ; Mapper 30, vertical mirroring, battery (self-flashable config with no bus conflicts)
.byte $10 ; Flags
.byte 0,0,0,0,0,0,0,0

CRUNCHY_SPRITE_PAGE = $200

CRUNCHY_TEMP                 = $00
CRUNCHY_VARS                 = $10
TOKUMARU_DECOMPRESS_MEM_BASE = $20

;
; Declare macro for bank-switching. This can be a trivial one as CrunchyView disables NMIs during picture loading.
;
.MACRO CRUNCHY_BANK_SWITCH_A
    sta $C000
.ENDM

.org $8000
.include "crunchylib.asm"

.org $C000
.include "crunchyview.asm"

.org $fffa
.word NMI
.word RESET
.word IRQ
