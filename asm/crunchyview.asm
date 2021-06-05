JOY_A                       = %10000000
JOY_B                       = %01000000
JOY_SELECT                  = %00100000
JOY_START                   = %00010000
JOY_UP                      = %00001000
JOY_DOWN                    = %00000100
JOY_LEFT                    = %00000010
JOY_RIGHT                   = %00000001

tempWord                    = $80
tempByte                    = $82
joy                         = $83
joyP                        = $85
vblankCounter               = $87
insideNMI                   = $88

; Disallows the split from being too low and leaving too little frame time remaining
MAX_DISPLAY_SCANLINES = 204

RESET:
    sei
    cld
    ldx #$FF
    txs
    inx
    stx $2000
    stx $2001

@waitWarmUpLoop1:
    lda $2002
    bpl @waitWarmUpLoop1

@waitWarmUpLoop2:
    lda $2002
    bpl @waitWarmUpLoop2
    
    ; Select 16kb bank 0 at $8000-$BFFF
    lda #0
    sta $C000
    jmp MainCode

MainCode:
    lda #$C0
    sta $4017
    cli
    jsr ClearRAM
    jsr ClearVRAM

    lda #$10
    ora #CRUNCHY_8x16_PPUCTRL_BITMASK
    sta $2000

    lda #$80
    sta CrunchyVar_ensureSprite0Hit

    ldy #0
    jsr ReloadPicture

    lda #$1E
    sta CrunchyVar_R2001
    ; Start from displaying full picture
    lda #240
    sta CrunchyVar_displayScanlines

    lda #$20
    sta $2006
    lda #$00
    sta $2006

    lda #$1E
    sta $2001
    lda #$90
    sta $2000
 
    lda #$1E
    sta CrunchyVar_R2001
    lda #$90
    sta $2000

@loop:
    ; Process joypad input
    jsr ReadJoypads
    jsr HandleInput
    ; Re-write OAM
    ldy CrunchyVar_pictureIndex
    jsr CrunchyLib_WriteOAM
    ; Wait for next frame
    lda vblankCounter
@waitOneFrameLoop:
    cmp vblankCounter
    beq @waitOneFrameLoop
    jmp @loop

HandleInput:
    @joyOrJoyP = tempByte

    jsr @handleColorEmphasis

    ldx joy
    txa
    and #JOY_A
    beq @dontDoStepVariant
    ; Replace joy with joyP to get step-variant for fine-tuning
    ldx joyP
@dontDoStepVariant:
    stx @joyOrJoyP

    lda joy
    and #JOY_SELECT
    bne @handleDisplayScanlinesAndSplitBank

    lda joy
    and #JOY_B
    bne @handleSplitScroll

    lda @joyOrJoyP
    and #JOY_START
    beq @skipIncImage
    jmp @IncImage
@skipIncImage:
    lda @joyOrJoyP
    and #JOY_RIGHT
    beq @skipIncScrollX
    jsr @IncScrollX
@skipIncScrollX:
    lda @joyOrJoyP
    and #JOY_LEFT
    beq @skipDecScrollX
    jsr @DecScrollX
@skipDecScrollX:
    lda @joyOrJoyP
    and #JOY_DOWN
    beq @skipIncScrollY
    jsr @IncScrollY
@skipIncScrollY:
    lda @joyOrJoyP
    and #JOY_UP
    beq @skipDecScrollY
    jsr @DecScrollY
@skipDecScrollY:
    rts

@handleSplitScroll:
    lda @joyOrJoyP
    and #JOY_RIGHT
    beq @skipIncSplitScrollX
    jsr @IncSplitScrollX
@skipIncSplitScrollX:
    lda @joyOrJoyP
    and #JOY_LEFT
    beq @skipDecSplitScrollX
    jsr @DecSplitScrollX
@skipDecSplitScrollX:
    lda @joyOrJoyP
    and #JOY_DOWN
    beq @skipIncSplitScrollY
    jsr @IncSplitScrollY
@skipIncSplitScrollY:
    lda @joyOrJoyP
    and #JOY_UP
    beq @skipDecSplitScrollY
    jsr @DecSplitScrollY
@skipDecSplitScrollY:
    rts


@handleDisplayScanlinesAndSplitBank:
    lda @joyOrJoyP
    and #JOY_DOWN
    beq @skipIncDS
    jsr @IncDS
@skipIncDS:
    lda @joyOrJoyP
    and #JOY_UP
    beq @skipDecDS
    jsr @DecDS
@skipDecDS:
    lda joyP
    and #JOY_RIGHT
    beq @skipIncBank
    jsr @IncBank
@skipIncBank:
    lda joyP
    and #JOY_LEFT
    beq @skipDecBank
    jsr @DecBank
@skipDecBank:
    rts

@IncDS:
    lda CrunchyVar_displayScanlines
    cmp #240
    bne @doIncDS
    ; Don't allow increasing beyond 240
    rts
@doIncDS:
    cmp #0
    beq @skipTo3
    clc
    adc #1
    cmp #MAX_DISPLAY_SCANLINES+1
    bne @dontSkipTo240
    ; Skip immediately to 240
    lda #240
@dontSkipTo240:
    sta CrunchyVar_displayScanlines
    rts
@skipTo3:
    lda #3
    sta CrunchyVar_displayScanlines
    rts

@DecDS:
    lda CrunchyVar_displayScanlines
    bne @doDecDS
    ; Don't allow decreasing beyond 0
    rts
@doDecDS:
    sec
    sbc #1
    cmp #2
    bne @dontSkipTo0
    ; Skip immediately to 0
    lda #0
@dontSkipTo0:
    cmp #239
    bne @dontSkipToMaxDisplayScanlines
    lda #MAX_DISPLAY_SCANLINES
@dontSkipToMaxDisplayScanlines:
    sta CrunchyVar_displayScanlines
    rts

@IncBank:
    lda CrunchyVar_splitChrBankBitsAndHiX
    asl
    rol tempByte
    lsr
    clc
    adc #(1 << 5)
    asl
    lsr tempByte
    ror
    sta CrunchyVar_splitChrBankBitsAndHiX
    rts

@DecBank:
    lda CrunchyVar_splitChrBankBitsAndHiX
    asl
    rol tempByte
    lsr
    sec
    sbc #(1 << 5)
    asl
    lsr tempByte
    ror
    sta CrunchyVar_splitChrBankBitsAndHiX
    rts

@IncScrollX:
    inc CrunchyVar_scrollX
    bne @skipIncScrollXHi
    inc CrunchyVar_scrollX+1
@skipIncScrollXHi:
    rts

@DecScrollX:
    lda CrunchyVar_scrollX
    sec
    sbc #1
    sta CrunchyVar_scrollX
    lda CrunchyVar_scrollX+1
    sbc #0
    sta CrunchyVar_scrollX+1
    rts

@IncScrollY:
    inc CrunchyVar_scrollY
    bne @skipIncScrollYHi
    inc CrunchyVar_scrollY+1
@skipIncScrollYHi:
    rts

@DecScrollY:
    lda CrunchyVar_scrollY
    sec
    sbc #1
    sta CrunchyVar_scrollY
    lda CrunchyVar_scrollY+1
    sbc #0
    sta CrunchyVar_scrollY+1
    rts

@IncSplitScrollX:
    inc CrunchyVar_splitScrollX
    bne @skipIncSplitScrollXHi
    lda CrunchyVar_splitChrBankBitsAndHiX
    eor #$80
    sta CrunchyVar_splitChrBankBitsAndHiX
@skipIncSplitScrollXHi:
    rts

@DecSplitScrollX:
    lda CrunchyVar_splitScrollX
    bne @skipDecSplitScrollXHi
    lda CrunchyVar_splitChrBankBitsAndHiX
    eor #$80
    sta CrunchyVar_splitChrBankBitsAndHiX
    lda CrunchyVar_splitScrollX
@skipDecSplitScrollXHi:
    sec
    sbc #1
    sta CrunchyVar_splitScrollX
    rts

@IncSplitScrollY:
    lda CrunchyVar_splitScrollY
    cmp #239
    bne @skipIncWrapY
    lda #255
@skipIncWrapY:
    clc
    adc #1
    sta CrunchyVar_splitScrollY
    rts

@DecSplitScrollY:
    lda CrunchyVar_splitScrollY
    bne @skipDecWrapY
    lda #240
@skipDecWrapY:
    sec
    sbc #1
    sta CrunchyVar_splitScrollY
    rts

@IncImage:
    lda CrunchyVar_pictureIndex
    clc
    adc #1
    cmp #CRUNCHY_NUM_PICTURES
    bne @IncImageInRange
    lda #0
@IncImageInRange:
    tay
    jmp ReloadPicture

@DecImage:
    dec CrunchyVar_pictureIndex
    bpl @DecImageInRange
    lda #CRUNCHY_NUM_PICTURES-1
    sta CrunchyVar_pictureIndex
@DecImageInRange:
    tay
    jmp ReloadPicture

@handleColorEmphasis:
    ; Make holding A/B/START on controller 2 affect color emphasis bits
    lda joy+1
    and #%11000000
    sta tempByte
    lda joy+1
    and #%00010000
    asl
    ora tempByte
    sta tempByte
    lda CrunchyVar_R2001
    and #$1F
    ora tempByte
    sta CrunchyVar_R2001
    rts

ReloadPicture:
    lda #0
    sta $2000
    sta $2001
    
    sty CrunchyVar_pictureIndex
    jsr LoadPicture
    
    lda #$1E
    sta $2001
    lda #$90
    sta $2000
    rts

LoadPicture:
    ; Always use nametable $2000 for demo viewer 
    lda #$20
    ; Always use banks 1-2 for demo viewer
    ldx #1
    ; Upload picture
    jsr CrunchyLib_LoadPicture
    rts

ClearRAM:
    ldx #0
    txa
@cleaRAMLoop:
    sta $000,x
    ;sta $100,x
    sta $200,x
    sta $300,x
    sta $400,x
    sta $500,x
    sta $600,x
    sta $700,x
    inx
    bne @cleaRAMLoop
    rts

ClearVRAM:
    lda #$00
    sta $2006
    sta $2006
    ldy #64
    ldx #0
@PageLoop:
@ByteLoop:
    sta $2007
    dex
    bne @ByteLoop
    dey
    bne @PageLoop
    rts

ReadJoypads:
    ldx #1
    stx $4016
    dex
    stx $4016
    inx
@ReadJoypadLoop:
    lda joy,x
    pha
    ldy #8
@ReadButtonLoop:
    lda $4016,x
    lsr
    rol joy,x
    dey
    bne @ReadButtonLoop
    pla
    eor joy,x
    and joy,x
    sta joyP,x
    dex
    bpl @ReadJoypadLoop
    rts

IRQ:
    rti

.ALIGN $100
NMI:
    bit insideNMI
    bpl @notInsideNMI
    ; BRK
    rti
@notInsideNMI:
    sec
    ror insideNMI
    pha
    txa
    pha
    tya
    pha

    lda $2002
    ; Do OAM DMA
    lda #0
    sta $2003
    lda #>CRUNCHY_SPRITE_PAGE
    sta $4014

    lda #$90
    ora #CRUNCHY_8x16_PPUCTRL_BITMASK
    ldx #0   ; Restore old scroll X to 0 when done
    jsr CrunchyLib_Display

    inc vblankCounter

    pla
    tay
    pla
    tax
    pla
    lsr insideNMI
    rti
