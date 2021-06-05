CRUNCHY_VARS_SIZE                       = 14
; X-scroll coordinate for picture (16 bits)
CrunchyVar_scrollX                      = CRUNCHY_VARS+0
; Y-scroll coordinate for picture (16 bits)
CrunchyVar_scrollY                      = CRUNCHY_VARS+2
; R2001 bits for picture
CrunchyVar_R2001                        = CRUNCHY_VARS+4
; X-scroll coordinate for bottom split section (8-bit)
CrunchyVar_splitScrollX                 = CRUNCHY_VARS+5
; Y-scroll coordinate for bottom split section (8-bit)
CrunchyVar_splitScrollY                 = CRUNCHY_VARS+6
; R2001 bits for split section
CrunchyVar_splitR2001                   = CRUNCHY_VARS+7
; Bits 5-6: First CHR bank used by bottom split section.
; Bit7: Hi bit of X-scroll coordinate for bottom split
CrunchyVar_splitChrBankBitsAndHiX       = CRUNCHY_VARS+8
; If bit7=1, sprite#0 hit will be ensured by forcing first two scanlines to not scroll
CrunchyVar_ensureSprite0Hit             = CRUNCHY_VARS+9
; Set by loading code to cache Y-coordinate for mid-frame CHR bank-switching
CrunchyVar_bottomStartScanline          = CRUNCHY_VARS+10
; Bits 5-6: First CHR bank used by picture
CrunchyVar_chrBankBits                  = CRUNCHY_VARS+11
; Number of scanlines to display picture before bottom split. Must be 3-240
CrunchyVar_displayScanlines             = CRUNCHY_VARS+12
; Current picture index. Used by loading and OAM write subroutines
CrunchyVar_pictureIndex                 = CRUNCHY_VARS+13

;
; Executes screen splits prepared by CrunchyLib_Display
;
; Must be aligned to a 256-byte memory page for timed code to take the right amount of cycles.
;
.ALIGN 256
CrunchyLib_DoSplits:
    @fracCycle      = CRUNCHY_TEMP+6
    @r2006B         = CRUNCHY_TEMP+11
    @numScanlines   = CRUNCHY_TEMP+12
    @numSections    = CRUNCHY_TEMP+13
    @tmp            = CRUNCHY_TEMP+14
    @returnBank     = CRUNCHY_TEMP+15
    ; First split is inside vblank, where we can just write scroll values trivially
    ; Pull X-scroll
    pla
    sta $2005
    ; Pull Y-scroll
    pla
    sta $2005
    ; Pull H + bank
    pla
    sta $C000
    sta @returnBank
    asl
    lda #0
    sta @fracCycle  ; Free-load on zero-load to initialise fractional cycle
    rol
    ora #($90 + CRUNCHY_8x16_PPUCTRL_BITMASK)
    sta $2000
    ; Pull R2001
    pla
    sta $2001
    ; Pull number of scanlines
    pla
    tay
    ; If this was the only section, we are done.
    dec @numSections
    beq @endOfSplits
    bit $2002
    bvs @vblankEndDetectable
    ; If sprite#0 ensuring was requested but no sprite#0 hit occurred in previous frame, just abort...
    ; CHR bank switching / partial frame won't be correct anyway, as we can't sync to end-of-vblank
    ; But return top CHR bank to hopefully hit sprite#0 next time
    ; Also pull our sections from stack before returning
@abortStackLoop:
    pla
    pla
    pla
    pla
    pla
    dec @numSections
    bne @abortStackLoop
    lda CrunchyVar_chrBankBits
    rts
@vblankEndDetectable:
    ; Wait for end of vblank
@waitForVBlankEnd:
    bit $2002
    bvs @waitForVBlankEnd
    ; assert(!VerticalBlank)
    jsr CrunchyLib_DelayScanlines
    lda $00
    nop
@splitsLoop:
    ; assert(!VerticalBlank)
    ; Pull X-scroll
    pla
    tax
    lsr
    lsr
    lsr
    sta @r2006B
    ; Pull Y-scroll
    pla
    tay
    asl
    asl
    and #$E0
    ora @r2006B
    sta @r2006B
    ; Pull H + bank
    pla
    sta @returnBank
    ; Write bit7 to H bit of $2006 (hi byte)
    and #$80
    asl
    rol
    asl
    asl
    sta $2006
    ; Write new bank
    lda @returnBank
    sty $2005
    ldy @r2006B
    sta $C000
    ; Delay to align with hblank
    ; assert(cycle > 240 && cycle < 290)
    stx $2005
    sty $2006
    ; Pull R2001
    pla
    sta $2001
    ; Pull number of scanlines
    pla
    tay
    ; if last section, there's nothing more to do - exit to reclaim rest of frame time
    dec @numSections
    beq @endOfSplits
    dey
    beq @skipDelay
    jsr CrunchyLib_DelayScanlines
@delayDone:
    jmp @splitsLoop
    ; Make sure to communicate correct return bank to caller
@endOfSplits:
    lda @returnBank
    and #%01100000
    rts

@skipDelay:
    ; Equivalent JSR + RTS = 12 cycles
    nop
    pha
    pla
    bne @delayDone
;
; Displays background and sprite overlay for specified number of scanlines
;
; Inputs:
;   Y: Number of scanlines to display
;   A: Nametable display selection (bit0-1 of $2000)
; Outputs:
;   A: CHR RAM bank or mask to use for rest of frame
;
CrunchyLib_Display:
    @numScanlinesTop            = CRUNCHY_TEMP+7
    @numScanlinesBottom         = CRUNCHY_TEMP+8
    @bankBits                   = CRUNCHY_TEMP+10
    @tmp                        = CRUNCHY_TEMP+12
    @numSections                = CRUNCHY_TEMP+13
    @HinBit7                    = CRUNCHY_TEMP+15
    
    ; Early-out if zero scanlines were requested
    ldy CrunchyVar_displayScanlines
    cpy #0
    bne @nonZeroScanlines
    ; No picture to display - return CHR bank#0 as default
    lda #(0 << 5)
    rts
@nonZeroScanlines:

    lda CrunchyVar_scrollX+1
    lsr
    lda #0
    ror
    sta @HinBit7

    lda CrunchyVar_chrBankBits
    ora #CRUNCHY_PRG_BANK
    ora @HinBit7
    sta @bankBits

    ldx CrunchyVar_pictureIndex
    lda CrunchyVar_bottomStartScanline
    cmp #240
    beq @dontShowBottomScanlines
    sec
    sbc CrunchyVar_scrollY
    sta @tmp
    ; Bottom number of scanlines
    tya
    sec
    sbc @tmp
    bcs @showBottomScanlines
    ; carry clear -> displayScanlines < BottomStartScanlineMinus1
    ; -> Don't display bottom part
@dontShowBottomScanlines:
    lda #0
@showBottomScanlines:
    sta @numScanlinesBottom
    ; For a non-bankswitched image, we always display the full displayScanlines
    lda CrunchyVar_displayScanlines
    ldx CrunchyVar_bottomStartScanline
    cpx #240
    beq @dontClampTopScanlines
    ; Top number of scanlines: min(displayScanlines, BottomStartScanline - scrollY)
    tya
    lda CrunchyVar_bottomStartScanline
    sec
    sbc CrunchyVar_scrollY
    cmp CrunchyVar_displayScanlines
    bcc @dontClampTopScanlines
    lda CrunchyVar_displayScanlines
@dontClampTopScanlines:
    ; assert(A > 2)
    sta @numScanlinesTop
;
; Prepare sections on stack to be consumed by timed screen-splits, starting from bottom
; TODO: Ideally this preparation work would be done outside of the precious vblank period.
; (...but OTOH with all the timed screen-splits, frame time might be equally precious)
;
    ldy #0
    lda CrunchyVar_displayScanlines
    cmp #239
    bcs @noPartialImageCutOff
    iny
    ; Push number of scanlines. (always one as we just restore old screen)
    lda #1
    pha
    ; Push R2001
    lda CrunchyVar_splitR2001
    pha
    ; Image ends early - end with section that restores original scrollX
    ; Push bank + H bit
    lda CrunchyVar_splitChrBankBitsAndHiX
    ora #CRUNCHY_PRG_BANK
    pha
    ; Push Y-scroll (set to same value as display scanlines to leave background "behind" unaffected)
    lda CrunchyVar_splitScrollY
    pha
    ; Push X-scroll
    lda CrunchyVar_splitScrollX
    pha
@noPartialImageCutOff:
    ; Conditionally do @bottomScanlines if non-zero
    ; (this section might not be present if requested display scanlines won't reach it,
    ;  or if image already fits in 256 BG tiles)
    lda @numScanlinesBottom
    beq @noBottomSection
    iny
    pha
     ; Push R2001
    lda CrunchyVar_R2001
    pha
    ; Push bank + H bit
    lda @bankBits
    clc
    adc #(1<<5)
    pha
    ; Push Y-scroll
    lda CrunchyVar_bottomStartScanline
    pha
    ; Push X-scroll
    lda CrunchyVar_scrollX
    pha
@noBottomSection:
    ; Conditionally do @topScanlines if non-zero
    ; Currently always present... even though image could in theory be scrolled up to hide it
    lda @numScanlinesTop
    beq @noTopSection
    iny
    ; Get number of scanlines and Y-scroll
    ; (nametable wrapped and potentially offset by 2 if sprite#0 hit handling is on)
    jsr CrunchyLib_GetTopModifiedNumScanlinesAndScrollY
    ; Push number of scanlines
    pha
    ; Push R2001
    lda CrunchyVar_R2001
    pha
    ; Push bank + H bit
    lda @bankBits
    pha
    ; Push Y-scroll
    txa
    pha
    ; Push X-scroll
    lda CrunchyVar_scrollX
    pha
@noTopSection:

    ; Conditionally do first two scanlines if sprite#0 hit ensuring has been requested
    bit CrunchyVar_ensureSprite0Hit
    bpl @noSprite0Section
    iny
    ; Push number of scanlines
    lda #2
    pha
    ; Push R2001
    lda CrunchyVar_R2001
    pha
    ; Push bank with H bit forced to 0
    lda @bankBits
    and #$7F
    pha
    ; Push X-scroll and Y-scroll to start (0,0)
    lda #0
    pha
    pha
@noSprite0Section:
    sty @numSections
    ; Execute sections
    jmp CrunchyLib_DoSplits

;
; Include Tokumaru's CHR decompression code
; (try to make all its branches fall within the same 256-byte page as a slight performance optimisation)
;
CrunchyLib_TokumaruDecompress:
.include "{OverlayPicPrefixDir}decompress.asm"

;
; Delays for a specified number of scanlines, + ? cycles (partial scanline)
;
CrunchyLib_DelayScanlines:
    @fracCycle      = CRUNCHY_TEMP+6
    ; assert(scanline < 239)
@delayScanlinesLoop:
    ldx #19
@delayScanlinesInnerLoop:
    dex
    bne @delayScanlinesInnerLoop
    clc
    lda @fracCycle
    adc #85
    sta @fracCycle
    bcc @extraCycle
@extraCycle:
    dey
    bne @delayScanlinesLoop
    rts

CrunchyLib_GetTopModifiedNumScanlinesAndScrollY:
    @numScanlinesTop            = CRUNCHY_TEMP+7
    @tmp                        = CRUNCHY_TEMP+11
    bit CrunchyVar_ensureSprite0Hit
    bmi @hasSprite0Section
    ; No sprite0 fudging - nothing to change except 240-height-wrap
    lda CrunchyVar_scrollY
    bit CrunchyVar_scrollY+1
    bpl @noSprite0SectionNowrap
    ; subtract 16 from Y-scroll coordinates to wrap 240 pixels high nametable
    sec
    sbc #16
@noSprite0SectionNowrap:
    tax
    lda @numScanlinesTop
    rts
@hasSprite0Section:
    ; scrollY += 2
    lda CrunchyVar_scrollY
    clc
    adc #2
    pha
    lda CrunchyVar_scrollY+1
    adc #0
    bpl @hasSprite0SectionNowrap
    ; subtract 16 from Y-scroll coordinates to wrap 240 pixels high nametable
    pla
    sec
    sbc #16
    jmp @skipPull
@hasSprite0SectionNowrap:
    pla
@skipPull:
    tax
    ; numScanlines -= 2
    lda @numScanlinesTop
    sec
    sbc #2
    rts

;
; Include data generated by crunchybuild
;
.include "{OverlayPicPrefixDir}includes.inc"

;
; Inputs:
;   Y = picture index
;   X = CHR bank number
;   A = High byte of nametable address
;
CrunchyLib_LoadPicture:
    ; Initialize pictureIndex
    sty CrunchyVar_pictureIndex
    ; Set no-display
    ldy #0
    sty CrunchyVar_displayScanlines
    pha ; (high byte of nametable address)
    ; Store CHR bank number into chrBankBits
    txa
    asl
    asl
    asl
    asl
    asl
    sta CrunchyVar_chrBankBits
    ; Decode all CHR data directly to PPU memory
    ldy CrunchyVar_pictureIndex
    jsr CrunchyLib_UploadCompressedCHR
    pla ; (high byte of nametable address)
    ; Decode nametable data directly to PPU memory
    ldy CrunchyVar_pictureIndex
    jsr CrunchyLib_UploadCompressedNametable
    ; Write palettes directly to PPU memory
    ldy CrunchyVar_pictureIndex
    jsr CrunchyLib_WritePalettes
    ; Clear OAM CPU page
    ldx #0
    lda #$F0
@oamClearLoop:
    sta CRUNCHY_SPRITE_PAGE,x
    inx
    bne @oamClearLoop
    ; Write OAM
    ldy CrunchyVar_pictureIndex
    jsr CrunchyLib_WriteOAM
; Reset first 10 variables to zero
    lda #0
    ldx #9
@resetVariablesLoop:
    sta CRUNCHY_VARS,x
    dex
    bpl @resetVariablesLoop
    ; Set flag to ensure sprite#0 hit
    lda #$80
    sta CrunchyVar_ensureSprite0Hit
    ; Display BG+sprites for picture
    lda #$1E
    sta CrunchyVar_R2001
    ; Display BG but hide sprites for split
    lda #$0E
    sta CrunchyVar_splitR2001
    ; Set 240 lines display
    lda #240
    sta CrunchyVar_displayScanlines
    rts

CrunchyLib_UploadCompressedNametable:
    @dataPtr    = CRUNCHY_TEMP
    ; Upload nametable
    sta $2006
    lda #$00
    sta $2006
    lda CrunchyData_NameTable_compressed_lo,y
    sta @dataPtr
    lda CrunchyData_NameTable_compressed_hi,y
    sta @dataPtr+1
@uploadLoop:
    jsr CrunchyLib_UploadCompressedNametableBlock
    ; Transfer Y offset to @dataPtr to keep decompressor indexing byte-sized
    ; (crunchybuild will always split nametables to enforce this limitation)
    tya
    clc
    adc @dataPtr
    sta @dataPtr
    lda @dataPtr+1
    adc #0
    sta @dataPtr+1
    ldy #0
    ; continue with next block unless zero-sized
    lda (@dataPtr),Y
    bne @uploadLoop
    rts

;
; Write coordinates ensuring a sprite#0 hit to first OAM entry
;
CrunchyLib_WriteSprite0ToOAM:
    lda #$FF
    ldx #CRUNCHY_8x16_PPUCTRL_BITMASK
    beq @sprites8x8
    lda #$FE
@sprites8x8:
    ; Tile index
    sta CRUNCHY_SPRITE_PAGE+1
    ; Attributes - use behind-background bit to hide sprite behind BG pixel
    lda #$20
    sta CRUNCHY_SPRITE_PAGE+2
    ; X = 248
    lda #248
    sta CRUNCHY_SPRITE_PAGE+3
    ; Y = 1 (sprite Y-coordinates is -1)
    lda #0
    sta CRUNCHY_SPRITE_PAGE
    rts

;
; Write all OAM for picture, including sprite#0
;
; Overlay sprites entries will be written to the end of OAM
;
CrunchyLib_WriteOAM:
    ; Write sprite#0 to OAM
    jsr CrunchyLib_WriteSprite0ToOAM
    ; Write rest of picture's OAM to *last* OAM entries, ending with sprite #63
    ldy CrunchyVar_pictureIndex
    lda #0
    sec
    sbc CrunchyData_NumSpriteTiles,y
    asl
    asl
    tax
    jsr CrunchyLib_WriteCompressedOAM
    rts

;
; Write compressed OAM directly to CPU memory page
;
; Input: Y = picture index
; Input: X = starting index in OAM
;
CrunchyLib_WriteCompressedOAM:
    @dataPtr    = CRUNCHY_TEMP
    @sprCount   = CRUNCHY_TEMP+2
    @tileIndex  = CRUNCHY_TEMP+3
    @spritePal  = CRUNCHY_TEMP+4

    lda CrunchyData_OAM_compressed_lo,y
    sta @dataPtr
    lda CrunchyData_OAM_compressed_hi,y
    sta @dataPtr+1
    lda CrunchyData_SpriteTilesStartIndex,y
    sta @tileIndex
    ldy #0
    ;
@palLoop:
    ; assert(Y < 136)
    lda #0
    sta @spritePal
    lda (@dataPtr),y
    bne @spritesRemaining
    ; No more sprites
    rts
@spritesRemaining:
    iny
    lsr
    rol @spritePal
    lsr
    rol @spritePal
    sta @sprCount
@oamSpriteLoop:
    ; assert(Y < 136)
    ; X-position
    lda (@dataPtr),y
    iny
    sec
    sbc CrunchyVar_scrollX
    sta CRUNCHY_SPRITE_PAGE+3,x
    lda #0
    sbc CrunchyVar_scrollX+1
    bne @spriteOutside
    ; assert(Y < 136)
    ; Y-position
    lda (@dataPtr),y
    sec
    sbc CrunchyVar_scrollY
    sta CRUNCHY_SPRITE_PAGE,x
    lda #0
    sbc CrunchyVar_scrollY+1
    bne @spriteOutside
    iny
    ; Tile index
    lda @tileIndex
    sta CRUNCHY_SPRITE_PAGE+1,x
    ; Palette
    lda @spritePal
    sta CRUNCHY_SPRITE_PAGE+2,x
@continueLoop:
    inx
    inx
    inx
    inx
    ; assert(X > 0)
    inc @tileIndex
.IF CRUNCHY_8x16_PPUCTRL_BITMASK
    inc @tileIndex
.ENDIF
    dec @sprCount
    bne @oamSpriteLoop
    jmp @palLoop

@spriteOutside:
    lda #240
    sta CRUNCHY_SPRITE_PAGE,x
    iny
    jmp @continueLoop

;
; Loads a picture's CHR data directly to PPU memory
;
; CHR data will be loaded to the bank set by CrunchyVar_chrBankBits.
; For a CHR-bank-switched image, the bottom part will also be loaded to the subsequent CHR bank.
;
CrunchyLib_UploadCompressedCHR:
    @dataPtr        = CRUNCHY_TEMP
    ;
    ; Upload BG CHR (top)
    ;
    lda CrunchyData_BottomStartScanlineMinus1,y
    sta CrunchyVar_bottomStartScanline
    inc CrunchyVar_bottomStartScanline
    jsr CrunchyLib_SwitchToTopCHR
    ; Upload BG CHR (top)
    lda CrunchyData_NumBackgroundTilesTop,y
    tax
    lda CrunchyData_BackgroundCHR_top_lo,y
    sta @dataPtr
    lda CrunchyData_BackgroundCHR_top_hi,y
    sta @dataPtr+1
    sec
    ldy #0
    jsr CrunchyLib_UploadTiles

    ; Upload Sprite CHR
    ldx #0
    ldy CrunchyVar_pictureIndex
    lda CrunchyData_SpriteCHR_lo,y
    sta @dataPtr
    lda CrunchyData_SpriteCHR_hi,y
    sta @dataPtr+1
    clc
    lda CrunchyData_NumSpriteTiles,y
    lda CrunchyData_SpriteTilesStartIndex,y
    tay
    jsr CrunchyLib_UploadTiles
    ldy CrunchyVar_pictureIndex
    lda CrunchyData_NumBackgroundTilesBottom,y
    bne @hasBottomCHR
    ; No bottom CHR - exit
    rts
@hasBottomCHR:
;
; Top -> bottom CHR copy
;
    ; Copy common BG CHR
    ldy CrunchyVar_pictureIndex
    lda CrunchyData_NumCommonBackgroundTilePages,y
    tax
    ldy #$10
    jsr CrunchyLib_CopyChrBankTopToBottom
    ; Copy sprite CHR
    ldy CrunchyVar_pictureIndex
    lda CrunchyData_NumSpriteTiles,y
    tax
    lda CrunchyData_SpriteTilesStartPage,y
    tay
    jsr CrunchyLib_CopyChrBankTopToBottom
    ; Upload BG CHR (bottom)
    jsr CrunchyLib_SwitchToBottomCHR
    ldy CrunchyVar_pictureIndex
    lda CrunchyData_BackgroundCHR_bottom_lo,y
    sta @dataPtr
    lda CrunchyData_BackgroundCHR_bottom_hi,y
    sta @dataPtr+1
    ldy CrunchyVar_pictureIndex
    lda CrunchyData_NumBackgroundTilesBottom,y
    tax
    lda CrunchyData_NumBackgroundTilesCommon,y
    tay
    sec
    jsr CrunchyLib_UploadTiles
    rts

;------------------------------------------------------------------------------

;
; Y = starting tile
; X = number of tiles
; C = CHR bank
; CRUNCHY_TEMP = Pointer to tile data
;
CrunchyLib_UploadTiles:
    @dataPtr = CRUNCHY_TEMP
    @temp    = CRUNCHY_TEMP+2
    @TokumaruDecompress_InputStream = TOKUMARU_DECOMPRESS_MEM_BASE + 18
    ;
    sty @temp
    lda #$00
    rol
    asl @temp
    rol
    asl @temp
    rol
    asl @temp
    rol
    asl @temp
    rol
    sta $2006
    lda @temp
    sta $2006
    ; Call Tokumaru decompressor
    lda @dataPtr
    sta @TokumaruDecompress_InputStream
    lda @dataPtr+1
    sta @TokumaruDecompress_InputStream+1
    jsr CrunchyLib_TokumaruDecompress
    rts

;
; Copy data from top to bottom CHR bank
;
; Inputs:
; Y: First 256-byte CHR page to copy
; X: Number of 256-byte CHR pages
;
CrunchyLib_CopyChrBankTopToBottom:
    lda CrunchyVar_chrBankBits
    ora #CRUNCHY_PRG_BANK
CrunchyLib_CopyChrToNextBank:
    @bankBits = CRUNCHY_TEMP
    sta @bankBits
@copyChrPageLoop:
    txa
    pha
    lda @bankBits
    ; Switch to this bank
    CRUNCHY_BANK_SWITCH_A
    jsr @setChrPageAddr
    ldx #0
    lda $2007
@readChrPageLoop:
    lda $2007
    sta $200,x
    inx
    bne @readChrPageLoop
    ; Switch to next bank
    lda @bankBits
    clc
    adc #(1 << 5)
    CRUNCHY_BANK_SWITCH_A
    jsr @setChrPageAddr
    ldx #0
@writeChrPageLoop:
    lda CRUNCHY_SPRITE_PAGE,x
    sta $2007
    inx
    bne @writeChrPageLoop

    iny
    pla
    tax
    dex
    bne @copyChrPageLoop
    rts

@setChrPageAddr:
    sty $2006 
    lda #0
    sta $2006
    rts

CrunchyLib_SwitchToTopCHR:
    lda #0
    bpl CrunchyLib_SwitchCHR
CrunchyLib_SwitchToBottomCHR:
    lda #(1<<5)
CrunchyLib_SwitchCHR:
    clc
    adc CrunchyVar_chrBankBits
    ora #CRUNCHY_PRG_BANK
    CRUNCHY_BANK_SWITCH_A
    rts

CrunchyLib_UploadCompressedNametableBlock:
    @dataPtr            = CRUNCHY_TEMP
    @oddNibble          = CRUNCHY_TEMP+2
    @rleAdd             = CRUNCHY_TEMP+3
    @rle_value          = CRUNCHY_TEMP+4
    @numBytesToDecode   = CRUNCHY_TEMP+6
    @nextNibble         = CRUNCHY_TEMP+8
    @rleinc_base        = CRUNCHY_TEMP+9
    @tmp                = CRUNCHY_TEMP+10
    @count              = CRUNCHY_TEMP+11
    ;
    ldy #0
    sty @rle_value
    sty @oddNibble
    lda (@dataPtr),y
    iny
    sta @numBytesToDecode
    lda (@dataPtr),y
    iny
    sta @rleinc_base

@UploadNametableLoop:
    cpy @numBytesToDecode
    bne @bytesRemaining
    bit @oddNibble
    bmi @isOddNibble
    rts
@isOddNibble:
    ; if no bytes left, 1-byte literal nibble can only signify end-of-compressed-block
    lda @nextNibble
    bne @bytesRemaining
    ; All bytes decoded
    rts
@bytesRemaining:
    lda #1
    sta @rleAdd
    jsr @ReadHeaderNibble
    beq @singleLiteral
    cmp #1
    beq @rleValueChange
    cmp #9
    bcs @rle
    bcc @rleInc

@rleValueChange:
    lda (@dataPtr),y
    iny
    sta @rle_value
    jmp @DecodeNext
@singleLiteral:
    jsr @readByteAndUpdateBase
    sta $2007
    jmp @DecodeNext

@rle:
    dec @rleAdd
    sec
    sbc #7
    tax
    cpx #8
    bne @rleNoExtended
    ; extended length - add next nibble to length
    pha
    stx @tmp
    jsr @ReadHeaderNibble
    clc
    adc @tmp
    tax
    pla
@rleNoExtended:
    lda @rle_value
    cmp @rleinc_base
    bcc @dontUpdateBaseRLE
    sta @rleinc_base
    inc @rleinc_base
@dontUpdateBaseRLE:
    
    jmp @rleLoopStart
@rleInc:
    tax
    lda @rleinc_base

    cpx #8
    bne @rleLoopStart
    ; extended length - add next nibble to length
    pha
    stx @tmp
    jsr @ReadHeaderNibble
    clc
    adc @tmp
    tax
    pla
@rleLoopStart:
    dex
@rleLoop:
    sta $2007
    clc
    adc @rleAdd
    dex
    bne @rleLoop

    ; if @rleAdd == 1 then new @rleinc_base needs to be last value +1
    dec @rleAdd
    bmi @wasNotRLEINC
    sta @rleinc_base
@wasNotRLEINC:

@DecodeNext:
    jmp @UploadNametableLoop

@ReadHeaderNibble:
    bit @oddNibble
    bpl @evenNibble
    lsr @oddNibble
    lda @nextNibble
    rts
@evenNibble:
    lda #$80
    sta @oddNibble
    lda (@dataPtr),y
    iny
    pha
    lsr
    lsr
    lsr
    lsr
    sta @nextNibble
    pla
    and #$0F
    rts

@readByteAndUpdateBase:
    lda (@dataPtr),y
    iny
    cmp @rleinc_base
    bcc @dontUpdateBase
    sta @rleinc_base
    inc @rleinc_base
@dontUpdateBase:
    rts

;
; Write a picture's background / sprite palettes to the PPU
;
; Inputs:
;   Y = picture index
;
CrunchyLib_WritePalettes:
    @dataPtr = CRUNCHY_TEMP
    ;
    lda CrunchyData_Palettes_lo,y
    sta @dataPtr
    lda CrunchyData_Palettes_hi,y
    sta @dataPtr+1
    lda #$3F
    sta $2006
    lda #$00
    sta $2006
    ldy #0
@writePaletteLoop:
    lda (@dataPtr),y
    sta $2007
    iny
    cpy #32
    bne @writePaletteLoop
    rts
