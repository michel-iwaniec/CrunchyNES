.SETCPU "6502X"

.segment "INESHDR"
.byte "NES",$1A
.byte 2   ; 2x16 kB PRG banks
.byte 0   ; 32kB switchable CHR RAM
.byte $E3 ; Mapper 30, vertical mirroring, battery (self-flashable config with no bus conflicts)
.byte $10 ; Flags
.byte 0,0,0,0,0,0,0,0

CRUNCHY_SPRITE_PAGE = $200

CRUNCHY_TEMP                 = $00
CRUNCHY_VARS                 = $10
TOKUMARU_DECOMPRESS_MEM_BASE = $20

.segment "CRUNCHYLIB"
.include "crunchylib.asm"

.CODE
.include "crunchyview.asm"

.segment "VECTORS"
.word NMI
.word RESET
.word IRQ
