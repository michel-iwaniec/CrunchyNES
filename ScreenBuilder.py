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
from array import array

from RLEiCompression import rleinc_compressed, MAX_COMPRESSED_BLOCK_SIZE

from typing import Tuple, List, Dict, Set, Optional, NewType

ByteArray = NewType('ByteArray', array)

import logging as log


@dataclass
class Cell:
    d: Tuple[int] = field(default_factory=tuple)    # Tile data
    i: int = 0                                      # Tile index
    p: int = 0                                      # Palette index


@dataclass
class Sprite:
    x: int          # X position
    y: int          # Y position
    i: int          # tile index
    H: bool         # Horizontal flip
    V: bool         # Vertical flip
    p: int          # Palette


class TileTable(UserList):
    NUM_TILE_PLANES = 2

    def __init__(self, max_tiles: int, width: int, height: int):
        super().__init__()
        self.max_tiles = max_tiles
        self.width = width
        self.height = height

    def add(self, tile_data: Tuple[int]) -> int:
        """
        Add tile data if not already in tile table, and return tile index.
        """
        assert(len(tile_data) == 2 * self.height)
        try:
            tile_index = self.data.index(tile_data)
        except ValueError:
            # Add missing tile_data
            tile_index = len(self.data)
            self.data.append(tile_data)
        return tile_index

    def tile_data(self, tile_index: int) -> Tuple[int]:
        """
        Return tile data for tile index
        
        :param tile_index: Tile index to return data for
        :return:           Tile data bytes
        """
        tile_size = self.height * self.NUM_TILE_PLANES
        return self.data[tile_index]  # * tile_size:(tile_index + 1) * tile_size]


TileTableType = NewType('TileTableType', TileTable)


class ScreenBuilder:
    NAMETABLE_WIDTH = 32
    NAMETABLE_HEIGHT = 30
    ATTRIBUTE_TABLE_WIDTH = 8
    ATTRIBUTE_TABLE_HEIGHT = 8

    TILE_WIDTH = 8
    TILE_HEIGHT = 8
    SPRITE_WIDTH = 8
    PALETTE_GROUP_SIZE = 4
    NUM_PALETTE_GROUPS_BG = 4
    NUM_PALETTE_GROUPS_SPR = 4
    NUM_TILE_PLANES = 2
    MAX_SPRITES = 64
    MAX_TILES_BG = 256

    """
    Builds a NES screen from an image
    
    A screen consists of:
    * Background tiles
    * Sprite tiles
    * Nametable
    * Sprite OAM
    """

    def __init__(self, image, sprites_8x16: bool, add_sprite0: bool, max_bg_slots: int):
        self.handle_sprite0_hit = True
        self.bottom_start_row = None  # Initialise with None for no-screen-split
        self.sprites_8x16 = sprites_8x16
        self.image = image
        self.screen_width, self.screen_height = image.size
        self.grid_width = self.screen_width // self.TILE_WIDTH
        self.grid_height = self.screen_height // self.TILE_HEIGHT
        #
        self.tile_table_bg = TileTable(max_tiles=2 * max_bg_slots - self.reserved_tiles_bg,
                                       width=self.TILE_WIDTH,
                                       height=self.TILE_HEIGHT)
        sprite_height_multiplier = 2 if self.sprites_8x16 else 1
        self.tile_table_spr = TileTable(64,
                                        width=self.TILE_WIDTH,
                                        height=self.TILE_HEIGHT * sprite_height_multiplier)
        # Make background layer
        self.make_background()
        # If > max_bg_slots, split/remap background layer into two dedicated tile tables
        if len(self.tile_table_bg) > max_bg_slots - self.reserved_tiles_bg:
            # Split into two tile tables and remap background
            self.split_background_tile_table(max_bg_slots)
        else:
            # Tiles fit into one table - make the other one a dummy
            self.tile_table_bg_top = self.tile_table_bg
            self.tile_table_bg_bottom = TileTable(max_bg_slots, self.TILE_WIDTH, self.TILE_HEIGHT)
            self.num_common_tile_indices = 0
        # Make sprite layer
        self.make_sprites()
        # Add sprite#0 hit tiles
        if add_sprite0:
            self.make_sprite0_hit_tiles()

    @property
    def reserved_tiles_bg(self) -> int:
        """
        Number of reserved background tiles
        
        :return: Number of reserved background tiles
        """
        return int(self.handle_sprite0_hit)

    @property
    def sprite_tiles_start_page(self) -> int:
        """
        Starting 256-byte page for sprite tiles.
        Sprite tiles are placed at the end of the bank, to provide more 
        predictable space for users to add their own sprite tiles.
        
        :return: Starting 256-byte page to upload sprites CHR to
        """
        tile_size = self.TILE_HEIGHT * self.NUM_TILE_PLANES
        return (self.sprite_tiles_start_index * tile_size) // 256

    @property
    def sprite_tiles_start_index(self) -> int:
        """
        First sprite tile to upload sprite CHR to.
        (this is 8x8, irrespective of 8x8 / 8x16 mode)
        
        :return: Starting tile index to upload sprite CHR to
        """
        num_sprite_tiles = len(self.sprites) + 1
        start_index = 256 - (num_sprite_tiles << int(self.sprites_8x16))
        return start_index

    def make_sprite0_hit_tiles(self):
        """
        Adds a single background pixel in the upper-right corner,
        along with a sprite to ensure sprite#0 hit is always triggered.
        """
        # PPU limitations:
        #   1) Sprite#0 hit cannot happen on x=255
        #   2) First scanline won't render sprites
        #
        # Either clone or re-use the 8x8 BG tile at 31x0 in nametable, and place opaque pixel at
        # (x, y) = (6, 1)
        # Then create a sprite tile with an opaque pixel at (x, y) = (6, 0) and place it at
        # screen coordinates (x, y) = (248, 1)
        # This makes the sprite#0 minimally intrusive but functional when blanking leftmost column
        #
        tile_index = self.background[31][0].i
        tile_data = list(self.tile_table_bg_top.tile_data(tile_index))
        # Set opaque pixel at (6, 1)
        tile_data[1] |= 0x02
        tile_index_new = self.tile_table_bg_top.add(tile_data)
        self.background[31][0].i = tile_index_new
        # Sprite tile with single pixel at (6, 0)
        spr_tile_size = self.tile_table_spr.NUM_TILE_PLANES * self.tile_table_spr.height
        spr_tile_data = [0] * spr_tile_size
        spr_tile_data[0] = 0x02
        self.tile_table_spr.add(tuple(spr_tile_data))

    def read_background_cell(self, image, x: int, y: int, w: int, h: int) -> Cell:
        """
        Read background cell from image
        
        :param image: image
        :param x:     x position of cell
        :param y:     y position of cell
        :param w:     width of cell
        :param h:     height of cell
        :return:      Cell object
        """
        return self.read_cell(image, x, y, w, h, False)

    def read_sprite_cell(self, image, x: int, y: int, w: int, h: int, palette_filter: int) -> Cell:
        """
        Read sprite cell from image
        
        :param image:          image
        :param x:              x position of cell
        :param y:              y position of cell
        :param w:              width of cell
        :param h:              height of cell
        :param palette_filter: Index of palette group to use for reading
        :return:               Cell object
        """
        return self.read_cell(image, x, y, w, h, True, palette_filter)

    def read_cell(self, image, start_x: int, start_y: int, w: int, h: int, sprite_cell: bool, palette_filter: Optional[int] = None) -> Cell:
        """
        Read sprite cell from image
        
        :param image:          image
        :param start_x:        x position of cell
        :param start_y:        y position of cell
        :param w:              width of cell
        :param h:              height of cell
        :param sprite_cell:    If true, read sprite cell. Otherwise read background cell
        :param palette_filter: Index of palette group to use for reading
        :return:               Cell object
        """
        background_cell = not sprite_cell
        cell = Cell(i=-1, p=None)
        tile_data = [0] * self.NUM_TILE_PLANES * h
        tile_p = None
        px_old = None
        py_old = None
        for y in range(h):
            for x in range(w):
                px = start_x + x
                py = start_y + y
                c = image.getpixel((px, py))
                if c % self.PALETTE_GROUP_SIZE != 0:
                    p = c // self.PALETTE_GROUP_SIZE
                    background_match = (background_cell and p < self.NUM_PALETTE_GROUPS_BG)
                    sprite_match = (palette_filter == p) or ((not palette_filter) and sprite_cell and p >= self.NUM_PALETTE_GROUPS_BG)
                    if background_match or sprite_match:
                        # Calculate additional offset in case we are reading an 8x16 tile
                        offs = (y // self.TILE_HEIGHT) * self.TILE_HEIGHT * self.NUM_TILE_PLANES
                        # P0
                        tile_data[offs + (y % self.TILE_HEIGHT)] |= ((c >> 0) & 1) << (w - 1 - x)
                        # P1
                        tile_data[offs + (y % self.TILE_HEIGHT) + self.TILE_HEIGHT] |= ((c >> 1) & 1) << (w - 1 - x)
                        # Check for inconsistency
                        if tile_p is not None and tile_p != p:
                            type_str = 'sprite' if sprite_cell else 'background'
                            log.error(f'Inconsistent {type_str} palette. {p} at pixel ({px},{py}) differs from {tile_p} at pixel ({px_old},{py_old})')
                            px_old = px
                            py_old = py
                        tile_p = p
        # Empty tile should default to palette index 0
        if tile_p is None:
            tile_p = 0
        # All-zero sprite tiles don't need storing
        if sprite_cell and sum(tile_data) == 0:
            return None, tile_p
        else:
            return tuple(tile_data), tile_p

    def make_background(self):
        """
        Create background layer.
        """
        self.background = [[Cell() for y in range(self.grid_height)] for x in range(self.grid_width)]
        w = self.grid_width
        h = self.grid_height
        cell_width = self.TILE_WIDTH
        cell_height = self.TILE_HEIGHT
        for y in range(h):
            for x in range(w):
                tile_data, tile_p = self.read_background_cell(self.image,
                                                              x * cell_width,
                                                              y * cell_height,
                                                              cell_width,
                                                              cell_height)
                tile_index = self.tile_table_bg.add(tile_data)
                # Add cell to background layer
                self.background[x][y] = Cell(d=tile_data, i=tile_index, p=tile_p)

    @staticmethod
    def _find_unique_tile_indices_per_row(layer: List[List[Cell]]) -> List[Set[int]]:
        w = len(layer)
        h = len(layer[0])
        unique_tile_indices_per_row = [set() for y in range(h)]
        for y in range(h):
            unique_tile_indices_per_row[y].update([layer[x][y].i for x in range(w)])
        return unique_tile_indices_per_row

    def _find_best_split(self, tile_table: TileTable, layer: List[List[Cell]], max_tiles: int) -> int:
        # Get the unique tiles used for every row
        indices_per_row = self._find_unique_tile_indices_per_row(layer)
        # to get as much CPU time as possible, find the topmost split point that will fit
        # both split parts within max tile limit.
        bottom_tiles = set()
        for y in range(self.grid_height - 1, -1, -1):
            if len(bottom_tiles.union(indices_per_row[y])) <= min(max_tiles, 255):
                bottom_tiles.update(indices_per_row[y])
            else:
                return y + 1
        log.error(f'Could not fit background tiles in just two pattern tables.')

    def _split_tile_table(self,
                          tile_table: TileTable,
                          indices_top: Set,
                          indices_bottom: Set,
                          indices_common: Set,
                          max_bg_slots: int) -> Tuple[TileTableType, Dict[int, int], TileTableType, Dict[int, int]]:
        tile_table_top = TileTable(max_bg_slots, self.TILE_WIDTH, self.TILE_HEIGHT)
        tile_table_bottom = TileTable(max_bg_slots, self.TILE_WIDTH, self.TILE_HEIGHT)
        remapping_top = {}
        remapping_bottom = {}
        # Add / remap common tile indices
        for i in sorted(indices_common):
            remapping_top[i] = len(tile_table_top)
            tile_table_top.append(tile_table[i])
            remapping_bottom[i] = len(tile_table_bottom)
            tile_table_bottom.append(tile_table[i])
        # Add / remap top tile indices
        for i in sorted(indices_top.difference(indices_common)):
            remapping_top[i] = len(tile_table_top)
            tile_table_top.append(tile_table[i])
        # Add / remap bottom tile indices
        for i in sorted(indices_bottom.difference(indices_common)):
            remapping_bottom[i] = len(tile_table_bottom)
            tile_table_bottom.append(tile_table[i])
        return tile_table_top, remapping_top, tile_table_bottom, remapping_bottom

    def _remap_background_indices(self, start: int, end: int, remapping: Dict[int, int]):
        w = self.grid_width
        for y in range(start, end):
            for x in range(self.grid_width):
                self.background[x][y].i = remapping[self.background[x][y].i]

    def split_background_tile_table(self, max_bg_slots: int):
        """
        Split background tile table into a top and bottom part
        """
        # Find best split
        self.bottom_start_row = self._find_best_split(self.tile_table_bg, self.background, max_bg_slots)
        unique_tile_indices_per_row = self._find_unique_tile_indices_per_row(self.background)
        # Find unique indices for top bottom, and common indices
        unique_top_tile_indices = set(itertools.chain(*unique_tile_indices_per_row[0:self.bottom_start_row]))
        unique_bottom_tile_indices = set(itertools.chain(*unique_tile_indices_per_row[self.bottom_start_row:]))
        unique_common_tile_indices = unique_top_tile_indices.intersection(unique_bottom_tile_indices)
        #
        self.tile_table_bg_top, remapping_top, self.tile_table_bg_bottom, remapping_bottom = self._split_tile_table(self.tile_table_bg,
                                                                                                                    unique_top_tile_indices,
                                                                                                                    unique_bottom_tile_indices,
                                                                                                                    unique_common_tile_indices,
                                                                                                                    max_bg_slots)
        self.num_common_tile_indices = len(unique_common_tile_indices)
        # Remap in-place
        self._remap_background_indices(0, self.bottom_start_row, remapping_top)
        self._remap_background_indices(self.bottom_start_row, self.grid_height, remapping_bottom)

    def merge_horizontally_adjacent_sprites(self, sprites: List[Sprite]) -> List[Sprite]:
        """
        Merges horizontally adjacent sprites with same palette and left + right
        padding that sums up to sprite width
        """
        def adjacent_slices(sprites: List[Sprite]) -> List[Sprite]:
            while len(sprites) > 0:
                for i in range(1, len(sprites)):
                    previous = sprites[i - 1]
                    if sprites[i].x != previous.x + self.SPRITE_WIDTH or sprites[i].y != previous.y or sprites[i].p != previous.p:
                        yield sprites[0:i]
                        sprites = sprites[i:]
                        break
                else:
                    yield sprites
                    return

        def get_paddings(sprite) -> Tuple[int, int]:
            """
            :param sprite: Sprite to get padding for
            :return:       Left and right padding
            """
            # bitwise-or to get union of pixels
            p = 0
            for b in sprite.tiledata:
                p |= b
            for l in range(self.SPRITE_WIDTH):
                if p & (0x80 >> l):
                    break
            for r in range(self.SPRITE_WIDTH):
                if p & (0x1 << r):
                    break
            return l, r
        #
        new_sprites = []
        for adjacent_slice in adjacent_slices(sprites):
            left_padding, _ = get_paddings(adjacent_slice[0])
            _, right_padding = get_paddings(adjacent_slice[-1])
            if left_padding + right_padding >= 8:
                # Move entire slice right by number of pixels given by left_padding
                for s in adjacent_slice:
                    s.x += left_padding
                adjacent_slice.pop()
            new_sprites.extend(adjacent_slice)
        return new_sprites

    def make_sprites(self):
        """
        Create sprite layer
        """
        #
        sprite_height_multiplier = 2 if self.sprites_8x16 else 1
        w = self.grid_width
        h = self.grid_height // sprite_height_multiplier
        sprite_grid = [[[Cell() for y in range(h)] for x in range(w)] for p in range(self.NUM_PALETTE_GROUPS_SPR)]
        for p in range(self.NUM_PALETTE_GROUPS_SPR):
            for y in range(h):
                for x in range(w):
                    tile_data, tile_p = self.read_sprite_cell(self.image,
                                                              x * self.TILE_WIDTH,
                                                              y * self.TILE_HEIGHT * sprite_height_multiplier,
                                                              self.TILE_WIDTH,
                                                              self.TILE_HEIGHT * sprite_height_multiplier,
                                                              p + self.NUM_PALETTE_GROUPS_BG)
                    # Add cell to sprite layer
                    sprite_grid[p][x][y] = Cell(d=tile_data, i=None, p=p + self.NUM_PALETTE_GROUPS_BG)
        # Convert gridded sprite layer to linear list of sprites
        self.sprites = []
        for p in range(self.NUM_PALETTE_GROUPS_SPR):
            for y in range(h):
                for x in range(w):
                    cell = sprite_grid[p - self.NUM_PALETTE_GROUPS_BG][x][y]
                    if cell.d:
                        tile_index = self.tile_table_spr.add(cell.d)
                        # Add sprite
                        s = Sprite(x=x * self.TILE_WIDTH,
                                   y=y * self.TILE_HEIGHT * sprite_height_multiplier,
                                   i=(tile_index << 1) if self.sprites_8x16 else tile_index,
                                   H=False,
                                   V=False,
                                   p=cell.p)
                        s.tiledata = cell.d
                        self.sprites.append(s)
        # Optimise sprites by reducing horizontally adjacent sprites
        self.sprites = self.merge_horizontally_adjacent_sprites(self.sprites)
        # Re-create new tile data for reduced adjacent sprites
        self.tile_table_spr.clear()
        start_index = self.sprite_tiles_start_page * (16 >> int(self.sprites_8x16))
        # Re-read tile_data for sprites, discarding those with empty tile data
        new_sprites = []
        for s in self.sprites:
            tile_data, tile_p = self.read_sprite_cell(self.image,
                                                      s.x,
                                                      s.y,
                                                      self.TILE_WIDTH,
                                                      self.TILE_HEIGHT * sprite_height_multiplier,
                                                      s.p)
            if tile_data is not None:
                self.tile_table_spr.add(tile_data) + start_index
                new_sprites.append(s)
        self.sprites = new_sprites
        if len(self.sprites) < 3:
            # Tokumaru compressor will crash if tiles < 3. Work-around this by padding
            # TODO: Fix in compressor instead
            while len(self.sprites) < 3:
                for i in range(1 + int(self.sprites_8x16)):
                    self.tile_table_spr.data.append(tuple([0 for i in range(self.TILE_HEIGHT * self.NUM_TILE_PLANES)]))
                # Add dummy sprite to match tile
                s = Sprite(x=0,
                               y=240,
                               i=0,
                               H=False,
                               V=False,
                               p=self.NUM_PALETTE_GROUPS_BG)
                self.sprites.append(s)
        if len(self.sprites) > self.MAX_SPRITES:
            log.error(f'Number-of-sprites overflow: {self.MAX_SPRITES}')
        # Re-number sprites as some may have been discarded after merging
        for i, s in enumerate(self.sprites):
            s.i = (i << 1) if self.sprites_8x16 else i

    @staticmethod
    def chr(tile_data: List[Tuple[int]]) -> ByteArray:
        """
        Convert tile data to byte array
        
        :param tile_data: List of tile data for each tile index
        :return:          Byte array of linearized tile data
        """
        chr_data = array('B', itertools.chain(*tile_data))
        return chr_data

    def chr_bg(self) -> ByteArray:
        """
        Get background CHR
        
        :return:          Byte array of linearized background tile data
        """
        return self.chr(self.tile_table_bg_top.data + self.tile_table_bg_bottom.data[self.num_common_tile_indices:])

    def chr_bg_top(self) -> ByteArray:
        """
        Get background CHR (top part)
        
        :return:          Byte array of linearized background tile data
        """
        return self.chr(self.tile_table_bg_top.data)

    def chr_bg_bottom(self) -> ByteArray:
        """
        Get background CHR (bottom part)
        
        :return:          Byte array of linearized background tile data
        """
        return self.chr(self.tile_table_bg_bottom.data)

    def chr_bg_bottom_no_common(self) -> ByteArray:
        """
        Get background CHR (bottom part without common tiles from top)
        
        :return:          Byte array of linearized background tile data
        """
        return self.chr(self.tile_table_bg_bottom.data[self.num_common_tile_indices:])

    def chr_spr(self) -> ByteArray:
        """
        Get sprite CHR
        
        :return:          Byte array of linearized background tile data
        """
        return self.chr(self.tile_table_spr.data)

    def nametable_without_attribute_table(self) -> ByteArray:
        """
        Get nametable data without attribute table
        
        :return:          Nametable as byte array
        """
        nt = array('B', [0] * self.grid_width * self.grid_height)
        for y in range(self.grid_height):
            for x in range(self.grid_width):
                nt[y * self.grid_width + x] = self.background[x][y].i
        return nt

    def _palette_index_table(self) -> List[List[int]]:
        w = self.NAMETABLE_WIDTH // 2
        h = self.NAMETABLE_HEIGHT // 2
        pt = [[0 for y in range(2 * self.ATTRIBUTE_TABLE_HEIGHT)] for x in range(2 * self.ATTRIBUTE_TABLE_WIDTH)]
        for y in range(h):
            for x in range(w):
                pt[x][y] = self.background[2 * x][2 * y].p | self.background[2 * x + 1][2 * y].p | self.background[2 * x][2 * y + 1].p | self.background[2 * x + 1][2 * y + 1].p
        return pt

    def attribute_table(self) -> ByteArray:
        """
        Get attribute table data
        
        :return:          Attribute table as byte array
        """
        # Get 16x16 palette-index table
        pt = self._palette_index_table()
        # Create 8x8 attribute table
        at = array('B', [0] * self.ATTRIBUTE_TABLE_WIDTH * self.ATTRIBUTE_TABLE_HEIGHT)
        for y in range(self.ATTRIBUTE_TABLE_HEIGHT):
            for x in range(self.ATTRIBUTE_TABLE_WIDTH):
                topLeft = pt[2 * x + 0][2 * y + 0]
                topRight = pt[2 * x + 1][2 * y + 0]
                bottomLeft = pt[2 * x + 0][2 * y + 1]
                bottomRight = pt[2 * x + 1][2 * y + 1]
                at[y * self.ATTRIBUTE_TABLE_WIDTH + x] = (bottomRight << 6) | (bottomLeft << 4) | (topRight << 2) | (topLeft << 0)
        return at

    def nametable(self) -> ByteArray:
        """
        Get nametable data
        
        :return:          Nametable as byte array
        """
        return self.nametable_without_attribute_table() + self.attribute_table()

    def split_nametable_in_half(self, rleinc_base_and_nametable: List[Tuple[int, List[int]]]) -> List[Tuple[int, List[int]]]:
        """
        Split nametable in half.
        
        :param rleinc_base_and_nametable: List of rleinc_base / nametable pairs
        :return:                          New list of rleinc_base / nametable pairs
        """
        def max_compressed_size(rleinc_base, nametable, row: int) -> int:
            nametable_top = nametable[0:self.NAMETABLE_WIDTH * row]
            nametable_bottom = nametable[self.NAMETABLE_WIDTH * row:]
            nametable_top_compressed, rleinc_base_new = rleinc_compressed(nametable_top, rleinc_base)
            nametable_bottom_compressed, _ = rleinc_compressed(nametable_bottom, rleinc_base_new)
            max_size = max([len(nametable_top_compressed), len(nametable_bottom_compressed)])
            return max_size
        rleinc_base, nametable = rleinc_base_and_nametable
        num_rows = len(nametable) // self.NAMETABLE_WIDTH
        row = num_rows // 2
        best_size = max_compressed_size(rleinc_base, nametable, row)
        while True:
            above_size = max_compressed_size(rleinc_base, nametable, row - 1) if row > 1 else None
            below_size = max_compressed_size(rleinc_base, nametable, row + 1) if row < num_rows - 1 else None
            if above_size < best_size and above_size <= below_size:
                best_size = above_size
                row = row - 1
                continue
            elif below_size < best_size:
                best_size = below_size
                row = row + 1
                continue
            else:
                break
        _, rleinc_base_new = rleinc_compressed(nametable[0:self.NAMETABLE_WIDTH * row], rleinc_base)
        return [(0, nametable[0:self.NAMETABLE_WIDTH * row]), (rleinc_base_new, nametable[self.NAMETABLE_WIDTH * row:])]

    def split_nametable(self, rleinc_base_and_nametable: List[Tuple[int, List[int]]]) -> List[Tuple[int, List[int]]]:
        """
        Split nametable in half.
        
        :param rleinc_base_and_nametable: List of rleinc_base / nametable pairs
        :return:                          New list of rleinc_base / nametable pairs
        """
        rleinc_base, nametable = rleinc_base_and_nametable
        if len(nametable) <= MAX_COMPRESSED_BLOCK_SIZE:
            return rleinc_base_and_nametable
        else:
            return self.split_nametable_in_half(rleinc_base_and_nametable)

    def nametable_compressed(self) -> ByteArray:
        """
        Get compressed nametable
        
        :return:          Compressed nametable as byte array
        """
        def add_header(compressed_nametable, rleinc_base: int):
            length_including_header = (len(compressed_nametable) + 2) & 0xFF
            compressed_nametable_with_length = array('B', compressed_nametable)
            compressed_nametable_with_length.insert(0, rleinc_base)
            compressed_nametable_with_length.insert(0, length_including_header)
            return compressed_nametable_with_length
        nametable = self.nametable()
        if self.bottom_start_row is not None:
            # if CHR-banked, start with mandatory split into two
            nametable_top = nametable[0:self.NAMETABLE_WIDTH * self.bottom_start_row]
            nametable_bottom = nametable[self.NAMETABLE_WIDTH * self.bottom_start_row:]
            nametables = [[self.num_common_tile_indices, nametable_top], [self.num_common_tile_indices, nametable_bottom]]
        else:
            # One single nametable
            nametables = [[self.num_common_tile_indices, nametable]]
        # Keep splitting resulting nametables in half until size matches maximum allowed compressed block size
        while any([len(rleinc_compressed(nametable, rleinc_base)[0]) > MAX_COMPRESSED_BLOCK_SIZE for rleinc_base, nametable in nametables]):
            for i, p in enumerate(nametables):
                rleinc_base = p[0]
                nametable = p[1]
                if len(rleinc_compressed(nametable, rleinc_base)[0]) > MAX_COMPRESSED_BLOCK_SIZE:
                    # split
                    split_nametables = self.split_nametable(p)
                    nametables = nametables[0:i] + split_nametables + nametables[i + 1:]
                    break
        # Compress final nametables and add header
        nametables_encoded = array('B', [])
        for rleinc_base, nametable in nametables:
            nametable_encoded, _ = rleinc_compressed(nametable, rleinc_base)
            nametables_encoded += add_header(nametable_encoded, rleinc_base)
        nametables_encoded += array('B', [0])
        return nametables_encoded

    def _sprite_to_oam_entry(self, sprite: Sprite) -> List[int]:
        oam_entry = []
        oam_entry.append(sprite.y - 1)
        oam_entry.append(sprite.i)
        oam_entry.append((sprite.V << 7) | (sprite.H << 6) | (sprite.p - self.NUM_PALETTE_GROUPS_BG))
        oam_entry.append(sprite.x)
        return oam_entry

    def oam(self) -> ByteArray:
        """
        Get raw OAM directly matching hardware format.
        
        :return:          OAM byte array
        """
        oam_data = [self._sprite_to_oam_entry(sprite) for sprite in self.sprites]
        return array('B', itertools.chain(*oam_data))

    def oam_compressed(self) -> ByteArray:
        """
        Get a "compressed" version of OAM.
        Compression consists of a simple ~50% reduction format:
        
        Initial byte:
          Bits 7-2: Number of sprites N
          Bits 1-0: Palette of sprites, with bits reversed.
        
        For each sprite 0..N-1
          Byte 0: X coordinate of sprite
          Byte 1: Y coordinate of sprite
        
        Tile index is assumed to start at 0 / 1 and linearly increasing
        by +1 / +2 for 8x8 / 8x16 sprites respectively.
        HFlip / VFlip / background priority is not supported.
        
        :return:          Compressed OAM byte array
        """
        sprites_per_pal = []
        for p in range(self.NUM_PALETTE_GROUPS_SPR):
            sprites_per_pal.append([sprite for sprite in self.sprites if sprite.p == (p + self.NUM_PALETTE_GROUPS_BG)])
        encoded_bytes = []
        tile_index = 0
        for p in range(self.NUM_PALETTE_GROUPS_SPR):
            if sprites_per_pal[p]:
                encoded_bytes.append((len(sprites_per_pal[p]) << 2) | ((p & 0x1) << 1) | ((p & 0x2) >> 1))
                for sprite in sprites_per_pal[p]:
                    assert sprite.p == p + ScreenBuilder.NUM_PALETTE_GROUPS_BG
                    assert not sprite.H and not sprite.V
                    assert sprite.i == tile_index
                    encoded_bytes.extend([sprite.x, sprite.y - 1])
                    tile_index += 2 if self.sprites_8x16 else 1
        # Zero-terminator byte
        encoded_bytes.append(0)
        return array('B', encoded_bytes)


ScreenBuilderType = NewType('BuilderType', ScreenBuilder)
