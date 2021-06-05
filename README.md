# CrunchyNES user guide

## Introduction

CrunchyNES is an image conversion flow and utility library targeting the 8-bit NES / Famicom hardware.

CrunchyNES aims to provide newcomers to NES development with a simple plug-n-play solution for displaying full-screen artwork on the NES for title screens, cutscenes and the like.

It employs three "semi-advanced" features often seen in classic NES games:
* Mid-frame CHR bank-switching to surpass the usual 256-tile count limit of backgrounds
* Sprite overlays placed on top of backgrounds to enable more colorful images
* Simple split-screen functionality that could be used for subtitles or animated cutscenes
* Data compression to allow more detailed pictures without losing too much ROM space

The assembly source currently targets UNROM-512 aka Mapper30 as it is the most popular mapper for NES homebrew games. Only the flashable Mapper30 variant with no bus conflicts is currently supported.

The included source supports both CA65 and asm6f / asm6 syntax, and the demo program CrunchyView can be built with either of these.

The tool generates data files for a a number of images, with a simple way to load their CHR / nametable / OAM / palette data by image index.

## Data compression used by CrunchyNES

### CHR compression

The CHR data is compressed using the highly efficient Tokumaru CHR compression scheme, itself a variant on the compression scheme used by Codemasters / Camerica in the NES's heyday. For more information please see the nesdev page on tile compression: https://wiki.nesdev.com/w/index.php/Tile_compression

### Nametable compression

Nametables are compressed using a simple RLE variant dubbed "RLEi". This format encodes nibbles indicating whether the next data byte is a run of tiles all increasing by +1 starting from the last seen byte, or a run of identical tiles.

It's not a generally good compression format and would perform comparatively poorly on generic nametable data for levels. But it works quite well for nametables representing full-screen artwork, where tiles are continually increasing with the exception of single-color areas.

### OAM "compression"

Sprite OAM is barely compressed at all, but just uses a pair of X,Y coordinates and separation of sprites based on their 4 possible palettes. This reflects the need for OAM to require constant re-writing every frame in the case of scrolling pictures with sprite overlays. The format is highly likely to change in a future version.

## Installation

### Using the binary Windows distribution

For the Windows user with no intent to modify CrunchyBuild, a .zip archive with the CrunchyBuild.exe program precompiled can be downloaded from http://github.com/michel-iwaniec/CrunchyNES/releases

### Using the Python source scripts

Alternative, the http://github.com/michel-iwaniec/CrunchyNES/ repo can be cloned and the Python scripts modified if needed, by installing Python 3.6+ and then installing the 'pillow' image library.

   pip install pillow

You will also need to separately download the Tokumaru tile compressor:
http://membler-industries.com/tokumaru/tokumaru_tile_compression.7z

...and extract it to a directory tokumaru_tile_compression located next to the crunchybuild.py script.

If you go down this route, just replace all instances of "CrunchyBuild.exe" with crunchybuild.py in the following command-line examples.

## Image conversion

Before using the CrunchyLib library to display images, the images need to be converted / compressed with the CrunchyBuild tool.

CrunchyBuild takes a sequence of images and runs a conversion process to perform the following steps:

* Mappping the palette in the indexed image to produce a 32-byte palette of NES PPU hardware colors
* Extracting colors 16-31 in the indexed image into a sprite layer consisting of OAM entries / CHR data
* Extracting colors 0-15 in the indexed image into a background layer consisting of a nametable / CHR data
* Splitting a background layer requiring more than 256 tiles of CHR data into a top and bottom half
* Compressing the CHR data using Tokumaru's compress tool
* Compressing the nametable data using a simple Run Length Encoding scheme
* Building data tables which allow the CrunchyLib routines to reference the data with a single byte-sized index
* Writing data tables and copying source files into a single output directory for inclusion in your NES project

### Preparing images for CrunchyBuild

CrunchyBuild only takes .png images as input, and is a somewhat fussy eater.

More specifically, the images need to be indexed-color 8bit images of 256x240 resolution - the dimensions of a single NES nametable.
Furthermore, they are only allowed to use the first 32 colors, representing the combined 32 bytes long palette space of the NES PPU.

Color indices 0-15 will be used for the background layer, and color indices 16-31 for the sprite layer. Any background colors need to conform to the NES hardware's 16x16 grid color limitations.

Sprite colors will be allocated into rows of hardware sprites individually depending on the palettes defined by the higher bits of sprite colors. The sprite size needs to be set to either 8x16 or 8x8 at build time.

If you have a 256x240 image in RGB format that you believe can fit the NES hardware restrictions using a combination of background and sprites, you can prepare this image for CrunchyBuild using the OverlayPal conversion tool: https://github.com/michel-iwaniec/OverlayPal

OverlayPal will allocate and duplicate colors as necessary to conform to the background / sprite color restrictions, allowing you to save a new indexed-color image which crunchybuild can process.

### Knowing your RGB -> PPU mapping

While the indexed-color images accepted by CrunchyBuild can specify exactly what entry in the 32-byte PPU hardware palette a pixel should map to, exactly what hue of colors supported by the NES that entry should contain is a different matter. Image formats use RGB color. The NES PPU does not.

Those with experience in NES emulation will have noticed that colors can vary wildly between emulators, and that emulators might even offer multiple choices of NES palettes. Because the NES does not produce a native RGB signal and TVs interpreted the signal differently, there's no canonical answer for a mapping from the RGB values an image on your PC contains to the 6-bit color values the NES PPU uses.

So to convert images without getting unexpected results you should be specifying this color mapping when passing your images to CrunchyBuild.

#### Specifying the color mapping via a .pal file

One way of specifying the RGB -> PPU color mapping is with a 192-byte large .pal file. This contains a 24-bit RGB value for each of the 64 PPU entries and defines how the NES PPU's colors should map to RGB values. These .pal files are commonly used by most NES emulators.

If you've used OverlayPal to convert the image, you will have already chosen a .pal file as part of the image preparation.
Simply use the "--palette_file" argument to specify the path to the particular .pal file OverlayPal used for the RGB -> indexed image conversion.

    --palette_file /path/to/palgen.pal

If you have started drawing your image from a screenshot taken via a NES emulator, find the particular .pal file in your emulator's directory.

If you've done neither of these, just use any 192-byte .pal file and hope for the best. A default one is included with both OverlayPal and CrunchyNES.

#### Specifying the palette directly on the command line

Alternatively you can specify the background palette and sprite palette as 16 hex values on the command-line

    --bg_pal 1D xy xy xy 1D xy xy x 1D xy xy xy 1D xy xy xy --spr_pal 1D xy xy xy 1D xy xy xy 1D xy xy xy 1D xy xy xy

Where the "1D" denotes the common background color, and "xy" denotes arbitrary 2-digit hex values specifying PPU colors.

This is mainly intended for quick tests, and as such it is currently applies globally to all converted images in CrunchyBuild's output data. So in practice it'll only work well for converting a single image.

### Converting images

To convert the included test image with 8x16 sprite overlays:

CrunchyBuild.exe --input testimages/Bernie-converted.png --palette_file mypalette.pal --sprite_size 8x16 --output output_folder

To convert multiple images in the same build, just pass multiple filenames for --input.

### Output folder

The output folder created by CrunchyBuild will contain source code, .bat files, compressed data and uncompressed data files.

Only a subset of these files actually need to be included into your game engine. The other files are useful for debugging the build output, and building the stand-alone CrunchyView picture viewer.

#### Essential data output

The following essential output data is produced by CrunchyBuild.

For each image N, a set of files 
* bg_top_[N].tc
  - Contains the CHR data for top part of image, compressed with Tokumaru compression
* bg_bottom_[N].tc
  - Contains the CHR data for bottom part of image, compressed with Tokumaru compression
  - Will be zero 0 if no more than 256 background tiles are used
* spr_[N].tc
  - Contains the CHR data for sprite overlay layer, compressed with Tokumaru compression
* nametable_compressed_[N].bin
  - Nametable compressed with a simple RLE-encoding
* oam_compressed_[N].bin
  - OAM stored as 2-byte X/Y pairs
* palette_[N].bin
  - 32 byte PPU palette entries

#### Uncompressed data files for debugging purposes

Alongside the compressed files, a set of uncompressed files are also produced for debugging purposes.

* bg_top_[N].chr
  - Contains the uncompressed CHR data for bottom part of image
* bg_bottom_[N].chr
  - Contains the uncompressed CHR data for bottom part of image
  - Will be zero 0 if no more than 256 background tiles are used
* bg_bottom_[N]_nc.chr
  - Same as bg_bottom_[N].chr, but without the common tiles also present in top CHR
  - This is what's actually compressed to produce bg_bottom_[N].tc
* spr_[N].tc
  - Contains the uncompressed CHR data for the sprite overlay layer
* nametable_[N].nam
  - Uncompressed nametable data
* oam_[N].bin
  - Uncompressed OAM directly representing NES OAM entries

The bg_top_[N].chr / bg_bottom_[N].chr / nametable_[N].nam can be loaded into programs such as NES ScreenTool as a sanity check.

## CrunchyView stand-alone viewer

A simple viewer running on the NES is included and can be built directly from the output directory. This viewer serves as a concrete source code example showing how to use the CrunchyLib source and the CrunchyBuild tool's data output in your own game engine.

In addition, it also provides an easy way to view a set of full-screen images on real hardware before putting them into your NES game.

### Building CrunchyView

Pre-made .bat files for Windows are available for building CrunchyView with either the CA65 or asm6 assembler (or its fork asm6f).

Running either of these will produce a .nes ROM with your converted pictures embedded into it. This .nes ROM can be run on an emulator, flash cartridge or a flashable Mapper30 cartridge.

The assemblers' executables and source code can currently be downloaded from the following sites:

CA65: github.com/cc65/cc65
asm6f: github.com/freem/asm6f
ASM6: 3dscapture.com/NES/

Whilst all three assembler are supported, CA65 is the highly recommended choice for multiple reasons including its extensive integration with the Mesen NES emulator's debugger.

#### Building with the CA65 assembler

To build crunchyview with the CA65 assembler, make sure to have CA65 on your path and run the included batch file.

    cd output_folder
    assemble_ca65.bat

This will produce the output file main_ca65.nes.

#### Building with the asm6f assembler

To build crunchyview with the asm6f assembler, make sure to have asm6f on your path and run the included batch file.

    cd output_folder
    assemble_asm6f.bat
    
This will produce the output file main_asm6.nes.

#### Building with the asm6 assembler

Finally, you can also build crunchyview with the original asm6 assembler.

    cd output_folder
    assemble_asm6.bat

This will produce the output file main_asm6.nes.

## Using CrunchyView

Once CrunchyView has been built with a set of embedded pictures, it provides following Joypad-driven navigation:

* D-pad left / right / up / down
  - Scrolls image in X / Y direction
  - Hold A button for single-step movement
* D-pad up / down whilst holding SELECT button
  - Increases / decreases the number of displayed scanlines (useful for testing screen-splits)
  - Hold A button for single-step movement
* D-pad right / left whilst holding SELECT button
  - Increases / decreases the bank number used for the screen split.
  - bank#0 (initial value) will be initialised to all-clear tiles by CrunchyView
* Hold A / B / START on second Joypad
  - Temporarily turns on the blue / green / red emphasis bits in register $2001 to tint the video output.

## Integrating CrunchyLib and the compressed pictures into your own game

CrunchyLib has been designed to be configurable but easy to integrate. Once CrunchyBuild has produced an output folder, only a few steps steps are needed.

### Setting up CrunchyLib's memory usage

CrunchyLib uses both persistent and temporary variables, which all need to reside in the zeropage. 

To play nicely with other code your game engine is running, their starting address can be configured by setting a few constants just before you include crunchylib.asm.

* CRUNCHY_VARS (12 bytes, zeropage storage required)
  - Starting address of the persistent variables to control CrunchyLib's behavior
* CRUNCHY_TEMP (16 bytes, zeropage storage required)
  - Contains temporary variables used by CrunchyLib's subroutines
  - Used by both the NMI code and non-NMI code.
  - Can potentially be shared with your own temporary zeropage storage
* TOKUMARU_DECOMPRESS_MEM_BASE (32 bytes, zeropage storage required)
  - Only used during CHR upload by the Tokumaru CHR decompressor
  - Is allowed to overlap with CRUNCHY_TEMP as both won't be used simultaneously
* CRUNCHY_SPRITE_PAGE
  - Defines the CPU page for OAM memory
  - Is also used as temporary space by CHR uploading to copy data between CHR banks
  - After CHR upload completes, make sure you re-write your OAM page to avoid glitchy sprites

Both the loader code and the converted image data currently need to fit into a single 16kB bank which needs to have been supplied when executing CrunchyBuild. To integrate the CrunchyLib source code into your own, make sure you supply the exact 16kB bank number to CrunchyLib with the --prgbank parameter (defaults to bank #0)

Then, just define the memory locations and include the crunchylib.asm file generated in the output directory.

    CRUNCHY_VARS = $xx
    CRUNCHY_TEMP = $yy
    CRUNCHY_TOKUMARU_TEMP = $zz
    CRUNCHY_SPRITE_PAGE = $xyz
    .include "crunchylib.asm"

### Defining the CRUNCHY_BANK_SWITCH_A macro

To allow CrunchyLib's picture loading routines to be interrupted by an NMI playing music, you will likely need to store the current bankswitching configuration in your own engine's internal variables. For this reason, CrunchyNES requires you to define a macro CRUNCHY_BANK_SWITCH_A.

This macro must be defined before including crunchylib.asm and can be defined in CA65 macro syntax as:

    .MACRO CRUNCHY_BANK_SWITCH_A
        sta $C000
        sta MyOwnGameEngineVarBankBits
    .ENDMACRO

Or equally in ASM6 macro syntax:

    .MACRO CRUNCHY_BANK_SWITCH_A
        sta $C000
        sta MyOwnGameEngineVarBankBits
    .ENDM


You can also potentially use the CRUNCHY_BANK_SWITCH_A macro to implement support for some other mapper. But keep in mind that due to its strict timing requirements the NMI display code does *not* use this macro, and would have to be manually re-purposed.

### Calling the NMI display code

To correctly display pictures, CrunchyLib contains a sub-routine CrunchyLib_Display which has to be called in your NMI *before* the end of vblank.

Your music player is usually the last thing called in your NMI and will also tend to outlive the vblank period. So you would typically put the call to CrunchyCode_DisplayImage just before the call to the music player.

    ; Switch $8000-$BFFF to point at CrunchyLib's PRG bank
    lda #CRUNCHY_PRG_BANK
    sta $C000
    ; Wait for vblank end and display picture
    jsr CrunchyLib_Display

After CrunchyLib_Display completes, it will return the CHR bank number last set in bits 5-6 of the A register. Typically this CHR bank number should remain set to this value for the remaining duration of the frame.

Because Mapper30 uses the same register for PRG and CHR switching, it is vital that you store these bits into your game engine's own current-CHR-bank variable, so that this CHR bank remains set when PRG bank switching happens outside the NMI handler.

### Loading a picture

To load an image, call the CrunchyLib_LoadPicture subroutine with the following registers correctly set.

    ; Switch $8000-$BFFF to point at CrunchyLib's PRG bank
    lda #CRUNCHY_PRG_BANK
    sta $C000
    ldy #0      ; Index of picture to load 
    ldx #1      ; Index of first 8kB CHR bank to use for picture. (> 256 tiles uses two consecutive banks)
    lda #$20    ; High byte of nametable
    jsr CrunchyCode_LoadPicture

This will perform the CHR and nametable decompression, upload palettes and initialize OAM once.
Note that you need to disable rendering via $2001 before making this subroutine call, and re-enable it when done.

You can leave NMIs during loading if you wish, but must make sure they don't attempt to set any PPU registers.

### Customized loading

For more advanced uses you might want to do just parts of what CrunchyLib_LoadPicture does to load an image.

Typical examples would be:
* Delaying palette updates to be handled by your own engine code
* Pre-loading CHR data for multiple pictures into different CHR banks and then loading just the nametables for faster switching

The easiest way to do this customization is by far to just copy'n'paste the CrunchyLib_LoadPicture subroutine to a new specialized one which omits loading of certain parts. The code is structured to allow easily disabling the different loading parts as needed.

### Controlling the display of the picture

Once CrunchyLib_Display is being correctly called from your NMI handler, a set of variables will control how crunchylib displays your loaded picture. You would typically manipulate these outside of the NMI handler.

    CrunchyVar_scrollX - 16-bit X-scroll coordinate for picture
    CrunchyVar_scrollY - 16-bit Y-scroll coordinate for picture
    CrunchyVar_displayScanlines - Allows cutting off the picture early to produce a split-screen effect
    CrunchyVar_ensureSprite0Hit - When bit7 set the first two scanlines will be static to ensure a sprite#0 hit
    CrunchyVar_chrBankBits - Bits 5-6 of this byte contain the top CHR bank to use for displaying the picture
    CrunchyVar_R2001 - $2001 will be set to this value during picture display

#### Updating OAM

To correctly display a converted picture using the sprite colors 15-31, the sprite overlay needs to be written into Object Attribute Memory.

The CrunchyLib_LoadPicture sub-routine will initialize OAM once at the pre-configured CPU RAM page CRUNCHY_SPRITE_PAGE.
For displaying a static picture this initial loading is sufficient, and there's no need to re-write the OAM page. This can save you precious frame time.

On the other hand if you intend to scroll the displayed picture, the OAM page will typically need to be re-written each frame as follows.

    ; Switch $8000-$BFFF to point at CrunchyLib's PRG bank
    lda #CRUNCHY_PRG_BANK
    ora yourEnginesChrBankBits
    sta $C000
    ; Write sprite#0 and picture's overlay sprites
    jsr CrunchyLib_WriteOAM

#### Scrolling the image

The picture can be scrolled much like any NES background, by changing the CrunchyVar_scrollX / CrunchyVar_scrollY variables.

The CrunchyLib_Display subroutine will write these variables to the scrolling registers during the NMI.

Keep in mind that both of these scroll coordinates are effectively treated as 16-bit variables, to allow scrolling two nametables and scroll sprites offscreen.

Note: Pictures using mid-frame CHR bank-switching currently have a limitation / bug with Y-scrolling where you cannot scroll the CHR bank switching split-point beyond the top / bottom of the screen.

#### Full display

To display the full-screen image as is, set CrunchyVar_displayScanlines to 240.

    lda #240
    sta CrunchyVar_displayScanlines

#### No display

To skip full-screen image display entirely, set CrunchyVar_displayScanlines to 0.

    lda #0
    sta CrunchyVar_displayScanlines

#### Partial display (with split-screen)

To display a partial image starting at the top and ending early, set CrunchyVar_displayScanlines to any value larger than 3, 
and set the CrunchyVar_splitScrollX/Y variables appropriately.

    lda #160
    sta CrunchyVar_displayScanlines
    lda #0
    sta CrunchyVar_splitScrollX
    lda #0
    sta CrunchyVar_splitScrollY

The CrunchyLib_Display subroutine will then display the requested scanlines as normal, before ending the timed loops by restoring to bank 0, and writing CrunchyVar_splitScrollX / CrunchyVar_splitScrollY to the scroll registers.

This can be useful if for example you want to display text subtitles on the bottom of the screen using a different CHR bank. You could then set CrunchyLib to load pictures into CHR banks 1-2, and keep your standard text font in CHR bank 0.

However, use this feature with caution as for both bankswitched and non-bankswitched images alike it will need to wait for these number of scanlines before the final scroll values can be written. And due to the simplified no-IRQ system it will cause all this time to be wasted in delay loops - potentially leaving too little frame time left for your music / text engine and cause slowdowns.

Setting CrunchyVar_displayScanlines to values between 192 to 239 is not recommended unless you are very confident that your non-NMI code is fast enough to complete in the remaining scanlines.

The split-screen support can also be used for splitting the picture itself to a degree. But it should be noted that the overlay sprites won't be affected by the new scroll value. This would make any overlay sprites after the split to show up in the wrong location. A future version might allow more control over sprites / split points.

### Using your own sprites on top of the displayed picture

As long as you have hardware sprites to spare, it is possible to add your own sprites on top of the displayed picture. This can be useful if you for example wish to add some additional animation on top of the scrolling picture, like perhaps overlaying a talking mouth on a face for a cutscene that uses CrunchyLib to display pictures.

To make this easier a little easier, CrunchyBuild and CrunchyLib already make sure that all the sprite CHR data for a converted picture is placed at the *end* of the sprite pattern table. By always loading your own sprites from into CHR tile 0 and onwards, you can avoid clashing with the picture's CHR. Even when 8x16 sprites, you have 128 tiles spare for your own sprite objects.

Likewise, the CrunchyBuild_WriteOAM subroutine will write sprite#0 to sprite location 0 (duh...) but write the rest of the overlay sprites to the end of the OAM page. For static pictures, this allows you to draw your own sprites starting from sprite 0, with no need to touch the pre-initialised overlay sprites. 

Due to being placed earlier in OAM, your own sprites will also appear on top of any overlay sprites, which is usually the behavior you want.

### Using your own BG Tiles in the displayed pictures

It is also possible to combine the picture with your own background tiles. However, background tiles are currently hardcoded to start at 0, so you'll need to place your own tile at the end of the BG pattern table.

To use this strategy with a mid-frame CHR bank-switched image, you'll need to make CrunchyBuild reserve BG tile slots in two banks.
A command-line parameter --max_bg_slots exists for this purpose. Specify this to a multiple of 16 that will leave some space at the end of the pattern table for your own BG tiles.

### Sprite0 hit quirks

Chances are you've already heard of sprite#0 hit - likely taking the prize as the most inconvenient sync-to-display-output hardware design choice ever made in videogame history.

As CrunchyLib targets the IRQ-less Mapper30, it relies on sprite#0 hits for mid-frame CHR bank-switching / split screen support, in order to allow your own NMI code to take a variable number of cycles without affecting the timing of the mid-frame PPU register writes.

However, rather than waiting for the actual sprite#0 hit, CrunchyLib's NMI code uses the sprite#0 hit flag to wait for the vblank period to end, at which point the sprite#0 hit flag resets to zero. 

This wait-formethod greatly simplifies the logic and timing when scrolling the loaded picture. Without this simplification sprite#0 would have to be moved along with the background when scrolling is used, and the exact horizontal position accounted for.

#### sprite#0 hit detection in detail

A sprite#0 hit needs a pixel of sprite#0 to overlap with the non-shared background color. And with a fully scrolling image, it can be difficult to guarantee this hit using ad-hoc placement, especially if the background image scrolls offscreen. This typically forms a tedious part of NES graphics conversion.

To simplify all of this, will generate a background pixel and a sprite in the upper-right corner that ensures the sprite#0 hit will always occur and the bottom CHR part display correctly, provided that the first two displayed scanlines are forced to display the image from coordinates (0, 0)

While the typical old NTSC TV would clip the first two scanliens, they can potentially look distracting on a display that shows 240 scanlines. If you never use more than 256 background tiles or just use an IRQ-based method of your own choice, you can turn this off by clearing bit 7 of the variable CrunchyVar_ensureSprite0Hit.

You can also turn the solid background pixel in the picture off by specifying "--sprite0 0" on the command line when calling CrunchyBuild.

#### 1-frame display glitch

Because the CHR bank-switching and the split-screen support both rely on a sprite#0 hit having occurred in the *previous* frame, the very first frame that is drawn when you've enabled rendering will always produce glitched output for mid-frame CHR bank-switching / split-screen. Without the sprite#0 hit having taken place in the previous frame, there's just no way for the code to detect the exact end of vblank / start of rendering. And thus no way to know when to perform the split.

An easy way to completely hide this visual glitch is to always have at least 1 frame of delay where the background / sprite palette entries are set to a single color. If you're already doing a fade-from-black / fade-from-white reveal of the displayed picture you should never see this glitch in practice.
