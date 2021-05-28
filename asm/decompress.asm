;
; Tokumaru's CHR decompressor
;
; Originally downloaded from: http://membler-industries.com/tokumaru/tokumaru_tile_compression.7z
;
; Trivially modified to allow an .include into either CA65 or asm6 based assembly source, by removing:
;   * Anonymous labels (which have different syntax for CA65 and asm6)
;   * enums variable declarations
;
; https://wiki.nesdev.com/w/index.php/Tile_compression#Tokumaru
;

@ColorCount      = TOKUMARU_DECOMPRESS_MEM_BASE + 0
@NextColor0      = TOKUMARU_DECOMPRESS_MEM_BASE + 4
@NextColor1      = TOKUMARU_DECOMPRESS_MEM_BASE + 8
@NextColor2      = TOKUMARU_DECOMPRESS_MEM_BASE + 12
@SpecifiedColor  = TOKUMARU_DECOMPRESS_MEM_BASE + 16
@TempBit         = @SpecifiedColor
@CurrentColor    = TOKUMARU_DECOMPRESS_MEM_BASE + 17
@CurrentRow      = @CurrentColor
@InputStream     = TOKUMARU_DECOMPRESS_MEM_BASE + 18
@TileCount       = TOKUMARU_DECOMPRESS_MEM_BASE + 20
@BitBuffer       = TOKUMARU_DECOMPRESS_MEM_BASE + 21
@Plane0          = TOKUMARU_DECOMPRESS_MEM_BASE + 22
@Plane1          = TOKUMARU_DECOMPRESS_MEM_BASE + 23
@PlaneBuffer     = TOKUMARU_DECOMPRESS_MEM_BASE + 24

;decompresses a group of tiles from PRG-ROM to CHR-RAM
@Decompress:

    ;clear the bit buffer
    lda #$80
    sta @BitBuffer

    ;copy the tile count from the stream
    ldy #$00
    lda (@InputStream), y
    sta @TileCount
    iny

@StartBlock:

    ;start by specifying how many colors can follow color 3 and listing all of them
    ldx #$03

@ProcessColor:

    ;copy from the stream the number of colors that can follow the current one
    jsr @Read2Bits
    sta @ColorCount, x

    ;go process the next color if the current one is only followed by itself
    beq @AdvanceColor

    ;read from the stream the one color necessary to figure all of them out
    lda #$01
    sta @SpecifiedColor
    jsr @ReadBit
    bcc @ProcessColorSkipRead
    inc @SpecifiedColor
    jsr @ReadBit
    bcc @ProcessColorSkipRead
    inc @SpecifiedColor
@ProcessColorSkipRead:
    cpx @SpecifiedColor
    bcc @ListColors
    dec @SpecifiedColor

@ListColors:

    ;assume the color is going to be listed
    lda @SpecifiedColor
    pha

    ;go list the color if it's the only one that can follow the current one
    lda @ColorCount, x
    cmp #$02
    bcc @List1Color

    ;keep the color from being listed if only 2 colors follow the current one
    bne @FindColors
    pla

@FindColors:

    ;save a copy of the current color so that values can be compared to it
    stx @CurrentColor

    ;find the 2 colors that are not the current one or the specified one
    lda #$00
@FindColorsLoop:
    cmp @SpecifiedColor
    beq @FindColorsSkip
    cmp @CurrentColor
    beq @FindColorsSkip
    pha
    sec
@FindColorsSkip:
    adc #$00
    cmp #$04
    bne @FindColorsLoop

    ;skip listing the third color if only 2 can follow the current one
    lda @ColorCount, x
    cmp #$02
    beq @List2Colors

    ;write the third color that can follow the current one
    pla
    sta @NextColor2, x

@List2Colors:

    ;write the second color that can follow the current one
    pla
    sta @NextColor1, x

@List1Color:

    ;write the first color that can follow the current one
    pla
    sta @NextColor0, x

@AdvanceColor:

    ;move on to the next color if there are still colors left
    dex
    bpl @ProcessColor

    ;pretend that all pixels of the previous row used color 0
    lda #$00
    sta @Plane0
    sta @Plane1

@DecodeTile:

    ;prepare to decode 8 rows
    ldx #$07

@DecodeRow:

    ;decide between repeating the previous row or decoding a new one
    jsr @ReadBit
    bcs @WriteRow

    ;prepare the flag that will indicate the end of the row
    lda #$01
    sta @Plane1

    ;remember which row is being decoded
    stx @CurrentRow

    ;read a pixel from the stream and draw it
    jsr @Read2Bits
    bpl @DrawNewPixel

@CheckCount:

    ;go draw the pixel if its color can't be followed by any other
    lda @ColorCount, x
    beq @RepeatPixel

    ;decide between repeating the previous pixel or decoding a new one
    jsr @ReadBit
    bcs @RepeatPixel

    ;skip if more than one color can follow the current one
    lda @ColorCount, x
    cmp #$01
    bne @DecodeColor

    ;go draw the only color that follows the current one
    lda @NextColor0, x
    bcs @DrawNewPixel

@DecodeColor:

    ;decode a pixel from the stream
    jsr @ReadBit
    bcs @DecodeColor_noDrawNewPixel
    lda @NextColor0, x
    bcc @DrawNewPixel
@DecodeColor_noDrawNewPixel:
    lda @ColorCount, x
    cmp #$03
    bcc @DecodeColor_noReadBit
    jsr @ReadBit
    bcs @DecodeColor_NextColor2
@DecodeColor_noReadBit:
    lda @NextColor1, x
    bcc @DrawNewPixel
@DecodeColor_NextColor2:
    lda @NextColor2, x

@DrawNewPixel:

    ;make a copy of the pixel for the next iteration
    tax

@DrawPixel:

    ;draw the pixel to the row
    lsr
    rol @Plane0
    lsr
    rol @Plane1

    ;go process the next pixel if the row isn't done
    bcc @CheckCount

    ;restore the index of the row
    ldx @CurrentRow

@WriteRow:

    ;output the fist plane of the row and buffer the second one
    lda @Plane0
    sta $2007
    lda @Plane1
    sta @PlaneBuffer, x

    ;move on to the next row if there are still rows left
    dex
    bpl @DecodeRow

    ;output the second plane of the tile
    ldx #$07
@PlaneBufferLoop:
    lda @PlaneBuffer, x
    sta $2007
    dex
    bpl @PlaneBufferLoop

    ;return if there are no more tiles to decode
    dec @TileCount
    beq @Return

    ;decide between decoding another tile or starting a new block
    jsr @ReadBit
    bcc @DecodeTile
    jmp @StartBlock

@RepeatPixel:

    ;go draw a pixel of the same color as the previous one
    txa
    bpl @DrawPixel

@Read2Bits:

    ;read 2 bits from the stream and return them in the accumulator
    jsr @ReadBit
    rol @TempBit
    jsr @ReadBit
    lda @TempBit
    rol
    and #$03
    rts

@ReadBit:

    ;read a bit from the stream and return it in the carry flag
    asl @BitBuffer
    bne @Return

    lda (@InputStream), y
    iny
    bne @ReadBit_noPageInc
    inc @InputStream+1
@ReadBit_noPageInc:
    rol
    sta @BitBuffer

@Return:

    ;return
    rts
