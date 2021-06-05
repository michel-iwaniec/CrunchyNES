#!/usr/bin/env python3
import sys
import shutil
import subprocess
from distutils.util import strtobool
import argparse
import time
import itertools
from math import ceil
from operator import itemgetter
from PIL import Image
from pathlib import Path
from dataclasses import dataclass, field, asdict
from collections import UserList, defaultdict

from ScreenBuilder import ScreenBuilder, ByteArray, ScreenBuilderType, TileTableType

from typing import Optional, Tuple, List, Sequence, Dict, Set, NewType

import array

import logging as log

VERSION_STRING = "1.0"
BUILD_PREFIX_CONSTANT = 'CRUNCHY_'
BUILD_PREFIX_DATA = 'CrunchyData_'

def get_script_directory() -> Path:
    """
    Return path to current scripts directory.
    (or the executable if built with pyinstaller)
    
    :return: Path to directory of this script
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    # or a script file (e.g. `.py` / `.pyw`)
    elif __file__:
        return Path(__file__).parent

def nes_closest_palette_entry(rgb: Tuple[int, int, int], NESPaletteRGB: List[Tuple[int, int, int]]) -> int:
    def dist2(rgbA, rgbB):
        return sum((rgbA[i] - rgbB[i])**2 for i in range(3))
    minIndex = min(enumerate([dist2(rgb, nprgb) for i, nprgb in enumerate(NESPaletteRGB)]), key=itemgetter(1))[0]
    return minIndex


def to_triplets(data: List[int]) -> List[Tuple[int, int, int]]:
    assert(len(data) % 3 == 0)
    length = len(data) // 3
    data_triplets = []
    for i in range(length):
        data_triplets.append((data[3 * i + 0], data[3 * i + 1], data[3 * i + 2]))
    return data_triplets


def map_palette_to_PPU_colors(rgb_palette_image: List[int], rgb_palette_nes: List[int]) -> Tuple[List[int], List[int]]:
    rgb_palette_image = to_triplets(rgb_palette_image)
    rgb_palette_nes = to_triplets(rgb_palette_nes)
    rgb_palette_nes[0x0D] = (1000000, 1000000, 1000000)  # Prevent blacker-than-black
    nes_palette_colors = []
    for rgb_color in rgb_palette_image[0:32]:
        # print(rgb_color)
        closest_palette_entry = nes_closest_palette_entry(rgb_color, rgb_palette_nes)
        nes_palette_colors.append(closest_palette_entry)
    bg_palette = nes_palette_colors[0:16]
    spr_palette = nes_palette_colors[16:]
    return bg_palette, spr_palette


def tokumaru_compress(inputFilename: Path, outputFilename: Path):
    """
    Compress CHR file using Tokumaru compression

    See: https://wiki.nesdev.com/w/index.php/Tile_compression#Tokumaru
    """
    url = 'http://membler-industries.com/tokumaru/tokumaru_tile_compression.7z'
    exePath = get_script_directory() / 'tokumaru_tile_compression' / 'bin' / 'compress.exe'
    if not exePath.exists():
        log.error(f'{str(exePath)} is missing! - download from {url}')
        return
    if inputFilename.stat().st_size:
        result = subprocess.run([str(exePath),
                                 str(inputFilename),
                                 str(outputFilename)],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
    else:
        # Bottom CHR may be zero - but create zero-sized file for consistency
        outputFilename.touch()

def get_image_palette(image: Image) -> List[int]:
    """
    Reads the palette from an indexed PIL image and pads it with zeros
    to yield 256*3 = 768 bytes.
    
    This function is a work-around for PIL / Pillow's handling
    of truncated palettes, which append the palette index rather
    than black.
    
    :param image: Indexed image to get palette from
    :return:      Zero-padded palette with exactly 768 byte values
    """
    imagePaletteLength = len(image.palette.palette)
    imagePalette = image.getpalette()[0:imagePaletteLength]
    numFillerBytes = 768 - imagePaletteLength
    if numFillerBytes > 0:
        imagePalette += [0] * numFillerBytes
    return imagePalette

def build_image(image_path: Path,
                image_index: int,
                outputFolder: Path,
                nes_palette: Optional[List[int]],
                bg_palette: Optional[List[int]],
                spr_palette: Optional[List[int]],
                sprite_size_8x16: bool,
                sprite0: bool) -> ScreenBuilderType:
    """
    :param image_path:   Path to input image
    :param image_index:  Index of image in assembly source
    :param outputFolder: Folder to write data files to
    :param nes_palette:  NES color palette as linearized 64*RGB values
    :bg_palette:         NES PPU palette values for background palette. Unused if nes_palette is present
    :spr_palette:        NES PPU palette values for sprites palette. Unused if nes_palette is present
    :sprite_size_8x16:   If true, use 8x16 sprites
    :sprite0:            If true, generate dummy sprite in top-right corner to ensure sprite#0 hit
    :return:             ScreenBuilder object
    """
    image = Image.open(image_path)
    if image.mode != 'P':
        log.error(f'image {imagePath} is not an indexed-color image.')
    log.info(f'Converting image {image_path}')
    if nes_palette is not None:
        bg_palette, spr_palette = map_palette_to_PPU_colors(array.array('B', get_image_palette(image)), array.array('B', nes_palette))
    builder = ScreenBuilder(image, sprite_size_8x16, sprite0)
    # Write data for built image
    outputFolder.mkdir(exist_ok=True)
    # BG chr
    with open(outputFolder / f'bg_{image_index}.chr', 'wb') as f:
        builder.chr_bg().tofile(f)
    # BG chr (top)
    with open(outputFolder / f'bg_top_{image_index}.chr', 'wb') as f:
        builder.chr_bg_top().tofile(f)
    # BG chr (bottom)
    with open(outputFolder / f'bg_bottom_{image_index}.chr', 'wb') as f:
        builder.chr_bg_bottom().tofile(f)
    # BG chr (bottom no common)
    with open(outputFolder / f'bg_bottom_nc_{image_index}.chr', 'wb') as f:
        builder.chr_bg_bottom_no_common().tofile(f)
    # Sprite CHR
    with open(outputFolder / f'spr_{image_index}.chr', 'wb') as f:
        builder.chr_spr().tofile(f)
    # nametable
    with open(outputFolder / f'nametable_{image_index}.nam', 'wb') as f:
        builder.nametable().tofile(f)
    with open(outputFolder / f'nametable_compressed_{image_index}.bin', 'wb') as f:
        builder.nametable_compressed().tofile(f)
    # OAM
    with open(outputFolder / f'oam_{image_index}.bin', 'wb') as f:
        builder.oam().tofile(f)
    with open(outputFolder / f'oam_compressed_{image_index}.bin', 'wb') as f:
        builder.oam_compressed().tofile(f)
    # palette
    if not spr_palette:
        spr_palette = [bg_palette[0]] * 16
    with open(outputFolder / f'palettes_{image_index}.bin', 'wb') as f:
        array.array('B', bg_palette + spr_palette).tofile(f)
    # Compress CHR
    tokumaru_compress(outputFolder / f'bg_top_{image_index}.chr', outputFolder / f'bg_top_{image_index}.tc')
    tokumaru_compress(outputFolder / f'bg_bottom_nc_{image_index}.chr', outputFolder / f'bg_bottom_nc_{image_index}.tc')
    tokumaru_compress(outputFolder / f'spr_{image_index}.chr', outputFolder / f'spr_{image_index}.tc')
    # Log compression ratio
    has_bottom_bg = len(builder.tile_table_bg_bottom) > 0
    compressed_size_bg_top = Path(outputFolder / f'bg_top_{image_index}.tc').stat().st_size
    compressed_size_bg_bottom = Path(outputFolder / f'bg_bottom_nc_{image_index}.tc').stat().st_size if has_bottom_bg else 0
    compressed_size_spr = Path(outputFolder / f'spr_{image_index}.tc').stat().st_size
    uncompressed_size_bg_top = Path(outputFolder / f'bg_top_{image_index}.chr').stat().st_size
    uncompressed_size_bg_bottom = Path(outputFolder / f'bg_bottom_nc_{image_index}.chr').stat().st_size if has_bottom_bg else 0
    uncompressed_size_spr = Path(outputFolder / f'spr_{image_index}.chr').stat().st_size
    uncompressed_size = uncompressed_size_bg_top + uncompressed_size_bg_bottom + uncompressed_size_spr
    compressed_size = compressed_size_bg_top + compressed_size_bg_bottom + compressed_size_spr
    space_saving = 1.0 - compressed_size / uncompressed_size
    log.info(f'CHR size % of original: {100.0 * (1.0 - space_saving):.2f}%')
    log.info(f'CHR space saving %: {100.0 * space_saving:.2f}%')
    return builder


def hi_and_lo_bytes(name: str, indices: List[int]) -> str:
    """
    Create assembly source for separate table of lo / hi byte

    :param name:    Name of of label
    :param indices: Indices in table
    :return:        Assembly source string
    """
    lo_bytes_str = f'{name}_lo: .byte {",".join([f"<{name}_{i}" for i in indices])}'
    hi_bytes_str = f'{name}_hi: .byte {",".join([f">{name}_{i}" for i in indices])}'
    return '\n'.join([lo_bytes_str, hi_bytes_str])


def builder_bytes(name: str, builder_accessor, builders: List[ScreenBuilder]) -> str:
    """
    Create assembly source of byte values given by applying an accessor function
    to each ScreenBuilder in a list.

    :param name:             Label
    :param builder_accessor: Function to call for each builder
    :params builders:        List of ScreenBuilder objects
    :return:                 Assembly source string
    """
    values_str = ','.join([str(builder_accessor(builder)) for builder in builders])
    return f'{name}: .byte {values_str}'


def copy_template_file(input_folder: Path, input_filename: Path, output_folder, prefix_dir: str = ''):
    with open(output_folder / input_filename, 'wt') as f:
        text = open(input_folder / input_filename, 'rt').read()
        f.write(text.format(OverlayPicPrefixDir=prefix_dir))


def main(image_paths: List[Path],
         outputFolder: Path,
         logFilePath: Path,
         palette_file: Path,
         bg_palette: List[int],
         spr_palette: List[int],
         sprite_size_8x16: bool,
         sprite0: bool,
         prg_bank: int,
         prefix_dir: str):
    # Read NES palette mapping file if present
    if palette_file is not None:
        with open(palette_file, 'rb') as f:
            nes_palette = f.read(192)
    else:
        nes_palette = None
    # Build each image
    builders = []
    for i, image_path in enumerate(image_paths):
        builder = build_image(image_path, i, outputFolder, nes_palette, bg_palette, spr_palette, sprite_size_8x16, sprite0)
        builders.append(builder)
    # Constant symbols
    with open(outputFolder / 'constants.inc', 'wt') as f:
        print(f'{BUILD_PREFIX_CONSTANT}NUM_PICTURES = {len(image_paths)}', file=f)
        ppu_ctrl_bitmask = 0x20 if builder.sprites_8x16 else 0x00
        print(f'{BUILD_PREFIX_CONSTANT}8x16_PPUCTRL_BITMASK = ${ppu_ctrl_bitmask:02X}', file=f)
        print(f'{BUILD_PREFIX_CONSTANT}CHR_BANK_TOP = {1}', file=f)
        print(f'{BUILD_PREFIX_CONSTANT}CHR_BANK_BOTTOM = {2}', file=f)
        print(f'{BUILD_PREFIX_CONSTANT}PRG_BANK = {prg_bank}', file=f)
    # Main include file
    with open(outputFolder / 'includes.inc', 'wt') as f:
        chr_suffix = 'tc'
        image_indices = range(0, len(image_paths))
        # Write data
        for image_index in image_indices:
            print(f'{BUILD_PREFIX_DATA}BackgroundCHR_top_{image_index}: .incbin "{prefix_dir}bg_top_{image_index}.{chr_suffix}"', file=f)
            print(f'{BUILD_PREFIX_DATA}BackgroundCHR_bottom_{image_index}: .incbin "{prefix_dir}bg_bottom_nc_{image_index}.{chr_suffix}"', file=f)
            print(f'{BUILD_PREFIX_DATA}SpriteCHR_{image_index}: .incbin "{prefix_dir}spr_{image_index}.{chr_suffix}"', file=f)
            print(f'{BUILD_PREFIX_DATA}NameTable_compressed_{image_index}: .incbin "{prefix_dir}nametable_compressed_{image_index}.bin"', file=f)
            print(f'{BUILD_PREFIX_DATA}OAM_compressed_{image_index}: .incbin "{prefix_dir}oam_compressed_{image_index}.bin"', file=f)
            print(f'{BUILD_PREFIX_DATA}Palettes_{image_index}: .incbin "{prefix_dir}palettes_{image_index}.bin"', file=f)
        # Write data pointer tables
        print(hi_and_lo_bytes(f'{BUILD_PREFIX_DATA}BackgroundCHR_top', image_indices), file=f)
        print(hi_and_lo_bytes(f'{BUILD_PREFIX_DATA}BackgroundCHR_bottom', image_indices), file=f)
        print(hi_and_lo_bytes(f'{BUILD_PREFIX_DATA}SpriteCHR', image_indices), file=f)
        print(hi_and_lo_bytes(f'{BUILD_PREFIX_DATA}NameTable_compressed', image_indices), file=f)
        print(hi_and_lo_bytes(f'{BUILD_PREFIX_DATA}OAM_compressed', image_indices), file=f)
        print(hi_and_lo_bytes(f'{BUILD_PREFIX_DATA}Palettes', image_indices), file=f)
        # Write per-image tables
        print(builder_bytes(f'{BUILD_PREFIX_DATA}NumBackgroundTilesTop', lambda builder: len(builder.tile_table_bg_top), builders), file=f)
        print(builder_bytes(f'{BUILD_PREFIX_DATA}NumBackgroundTilesBottom', lambda builder: len(builder.tile_table_bg_bottom), builders), file=f)
        print(builder_bytes(f'{BUILD_PREFIX_DATA}NumBackgroundTilesCommon', lambda builder: builder.num_common_tile_indices, builders), file=f)
        print(builder_bytes(f'{BUILD_PREFIX_DATA}NumSpriteTiles', lambda builder: len(builder.tile_table_spr), builders), file=f)
        print(builder_bytes(f'{BUILD_PREFIX_DATA}OamSize', lambda builder: len(builder.oam()), builders), file=f)
        print(builder_bytes(f'{BUILD_PREFIX_DATA}NumSpriteTilePages', lambda builder: int(ceil(len(builder.tile_table_spr) / 16)), builders), file=f)
        print(builder_bytes(f'{BUILD_PREFIX_DATA}SpriteTilesStartIndex', lambda builder: builder.sprite_tiles_start_index, builders), file=f)
        print(builder_bytes(f'{BUILD_PREFIX_DATA}SpriteTilesStartPage', lambda builder: builder.sprite_tiles_start_page, builders), file=f)
        print(builder_bytes(f'{BUILD_PREFIX_DATA}NumCommonBackgroundTilePages', lambda builder: int(ceil(builder.num_common_tile_indices / 16)), builders), file=f)
        print(builder_bytes(f'{BUILD_PREFIX_DATA}BottomStartScanlineMinus1', lambda builder: builder.bottom_start_row * 8 - 1 if builder.bottom_start_row is not None else 239, builders), file=f)
        print(builder_bytes(f'{BUILD_PREFIX_DATA}NameTableEncodingBits', lambda builder: builder.bottom_start_row if builder.bottom_start_row is not None else 30, builders), file=f)
        # Write constants
        print(f'.include "{prefix_dir}constants.inc"', file=f)
    # Copy sources
    scriptFolder = get_script_directory()
    # CrunchyLib / CrunchyView
    copy_template_file(scriptFolder / 'asm', 'crunchylib.asm', outputFolder, prefix_dir)
    shutil.copy2(scriptFolder / 'asm' / 'crunchyview.asm', outputFolder)
    # Tokumaru decompressor
    shutil.copy2(scriptFolder / 'asm' / 'decompress.asm', outputFolder)
    # CA65 files
    shutil.copy2(scriptFolder / 'asm' / 'assemble_ca65.bat', outputFolder)
    shutil.copy2(scriptFolder / 'asm' / 'main_ca65.asm', outputFolder)
    shutil.copy2(scriptFolder / 'asm' / 'main_ca65.cfg', outputFolder)
    # asm6 files
    shutil.copy2(scriptFolder / 'asm' / 'assemble_asm6f.bat', outputFolder)
    shutil.copy2(scriptFolder / 'asm' / 'main_asm6.asm', outputFolder)


def get_pal_file_path(pal_file_path: str) -> Path:
    """
    Convert a string path to Pathlib path.
    If None, use default path and print warning message.
    If file is missing, print error.

    :param pal_file_path: path to .pal file
    :return: path as pathlib Path
    """
    default_pal_file_path = get_script_directory() / 'nespalettes' / 'default.pal'
    if pal_file_path is None:
        log.warning(f'Palette file not specified - falling back to default palette file {str(default_pal_file_path)}')
        return default_pal_file_path
    elif not Path(pal_file_path).exists():
        log.error(f'Palette file {str(Path(pal_file_path))} does not exist - falling back to default palette file {str(default_pal_file_path)}')
        return default_pal_file_path
    else:
        return Path(pal_file_path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=f'CrunchyNES image converter version {VERSION_STRING}')
    parser.add_argument('--input', type=str, required=True,
                        nargs='+',
                        help='Input image to convert')
    parser.add_argument('--output', type=str,
                        default='output',
                        help='Output directory')
    parser.add_argument('--log', type=str,
                        default='{output}/build.log',
                        help='Log file')
    parser.add_argument('--bg_pal', type=str,
                        nargs='+',
                        default=None,
                        help='Background palette directly specified as 16 hex-values representing NES PPU colors')
    parser.add_argument('--spr_pal', type=str,
                        nargs='+',
                        default=None,
                        help='Sprite palette directly specified as 16 hex-values representing NES PPU colors')
    parser.add_argument('--sprite_size', type=str,
                        default='8x16',
                        choices=['8x8', '8x16'],
                        help='Sprite size')
    parser.add_argument('--sprite0', type=int, default=1,
                        help='If 1, adds sprite + tile pixels to ensure sprite#0 hit will happen when displaying image')
    parser.add_argument('--prgbank', type=int,
                        default=0,
                        help='PRG bank assumed by generated code')
    parser.add_argument('--palette_file', type=str,
                        default=None,
                        help='Binary 192-byte file specifying a particular NES palette. '
                             'NES PPU colors will be created by color mapping')
    parser.add_argument('--prefix_dir', type=str,
                        default='',
                        help='Prefix directory path to prepend to files included in source. Must include trailing separator. '
                             'If using ASM6 as assembler this is needed to correctly use source directory instead of CWD.'
                             'With CA65 this parameter is redundant.')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose logging')
    args = parser.parse_args()

    # Configure logging
    log_level = log.INFO if args.verbose else log.ERROR
    log.basicConfig(format = '%(levelname)s: %(message)s', level = log_level)
    # Call main conversion program
    rc=main(args.input,
              Path(args.output),
              None,
              get_pal_file_path(args.palette_file) if ((args.bg_pal is None) or (args.spr_pal is None)) else None,
              [int(s, 16) for s in args.bg_pal] if args.bg_pal is not None else [],
              [int(s, 16) for s in args.spr_pal] if args.spr_pal is not None else [],
              args.sprite_size == '8x16',
              bool(args.sprite0),
              args.prgbank,
              args.prefix_dir)
    sys.exit(rc)
