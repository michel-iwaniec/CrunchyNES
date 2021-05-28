from array import array

from typing import Tuple, List, Sequence, Dict, Set, NewType

MIN_RLE_LENGTH = 1
MAX_RLE_LENGTH = 22
MAX_RLE_LENGTH_SHORT = 6
MAX_COMPRESSED_BLOCK_SIZE = 254


def rleinc_compressed(input_data: Sequence[int], rleinc_base: int) -> List[int]:
    """
    Simple RLE compression variant that is optimised for both repeating and linearly increasing values
    
    Stores encoding two nibbles at a time into a single byte, with 1 optional length nibble and one optional data byte following.
    Data bytes are never split, but always start on an even nibble.
    
    Compressed data should be decoded as follows:
    [Header bytes]
    1 byte denoting length of data (including header bytes)
    1 byte signifying the starting RLEINC value to use for incrementing RLE.
    [data nibbles]
    0     : Simply copy next byte from input to output
    1     : Set next byte as new RLEVALUE byte
    2-8   : Repeat RLEINC byte B 1-22* times, adding +1 to RLEINC after each time
    9-15  : Repeat RLEVALUE byte B 1-22* times
    
    *Whenever the length is > MAX_RLE_LENGTH_SHORT, the next nibble denotes the additional RLE / RLEINC length, from 0-15.
    """
    # Regular RLE
    def rle(v) -> int:
        first_byte = v[0]
        i = 0
        while i < len(v) and i < MAX_RLE_LENGTH and v[i] == first_byte:
            i += 1
        return i
    # RLE-inc

    def rleinc(v) -> int:
        first_byte = v[0]
        i = 0
        while i < len(v) and i < MAX_RLE_LENGTH and v[i] == first_byte + i:
            i += 1
        return i

    def encode_bytes(e: List[int]) -> List[int]:
        eb = []
        hdr_nibbles = []
        data_bytes = []
        last_nibble_extends = False
        while len(e) > 0:
            hdr, data = e[0]
            e = e[1:]
            last_nibble_extends = False
            if hdr == 0 or hdr == 1:
                hdr_nibbles.append(hdr)
                data_bytes.append(data)
            elif 2 <= hdr <= 8:
                # rle-inc
                hdr_nibbles.append(hdr)
                if hdr == 8:
                    hdr_nibbles.append(e[0][0])
                    data_bytes.append([])
                    e = e[1:]
                    last_nibble_extends = True
                data_bytes.append(data)
            else:
                # rle
                hdr_nibbles.append(hdr)
                if hdr == 15:
                    hdr_nibbles.append(e[0][0])
                    data_bytes.append([])
                    e = e[1:]
                    last_nibble_extends = True
                data_bytes.append(data)
            can_output = len(hdr_nibbles) == 2 or (len(hdr_nibbles) == 3 and (not last_nibble_extends)) or len(hdr_nibbles) == 4
            if can_output:
                # Output two nibbles in byte stream
                eb.append((hdr_nibbles[1] << 4) | hdr_nibbles[0])
                hdr_nibbles = hdr_nibbles[2:]
                eb.extend(data_bytes[0])
                eb.extend(data_bytes[1])
                data_bytes = data_bytes[2:]
            elif len(hdr_nibbles) == 5 and last_nibble_extends:
                # Output two nibbles in byte stream
                eb.append((hdr_nibbles[1] << 4) | hdr_nibbles[0])
                hdr_nibbles = hdr_nibbles[2:]
                eb.extend(data_bytes[0])
                eb.extend(data_bytes[1])
                data_bytes = data_bytes[2:]
        if len(hdr_nibbles) > 1:
            eb.append((hdr_nibbles[1] << 4) | hdr_nibbles[0])
            hdr_nibbles = hdr_nibbles[2:]
            eb.extend(data_bytes[0])
            eb.extend(data_bytes[1])
            data_bytes = data_bytes[2:]
        if len(hdr_nibbles) > 0:
            eb.append(hdr_nibbles[0])
            hdr_nibbles = hdr_nibbles[1:]
            eb.extend(data_bytes[0])
            data_bytes = data_bytes[1:]
        assert len(hdr_nibbles) == 0 and len(data_bytes) == 0
        return eb

    def skip_bytes(d: List[int], rleinc_base: int, num_bytes: int):
        rleinc_base_new = max(d[0:num_bytes]) + 1
        return d[num_bytes:], max([rleinc_base_new, rleinc_base])
    # Encode
    d = input_data[:]
    e = []
    rle_value = 0
    while len(d) > 0:
        # Attempt each encoding and find compression ratio
        rle_len = rle(d)
        rle_cr = 0.5 / rle_len if d[0] == rle_value else (0.5 + 0.5 + 1) / rle_len
        rleinc_len = rleinc(d)
        rleinc_cr = 0.5 / rleinc_len
        plain_1_cr = (0.5 + 1) / 1
        if rleinc_cr <= min([plain_1_cr, rle_cr]) and d[0] == rleinc_base and rleinc_len >= 1:
            # Encode incrementing RLE
            assert 1 <= rleinc_len <= MAX_RLE_LENGTH, 'Max RLEINC encoding wrong'
            if rleinc_len > MAX_RLE_LENGTH_SHORT:
                rleinc_len_first_nibble = MAX_RLE_LENGTH_SHORT + 1
            else:
                rleinc_len_first_nibble = rleinc_len
            e.append((rleinc_len_first_nibble + 1, []))
            d, rleinc_base = skip_bytes(d, rleinc_base, rleinc_len)
            if rleinc_len > MAX_RLE_LENGTH_SHORT:
                e.append((rleinc_len - (MAX_RLE_LENGTH_SHORT + 1), []))
        elif rle_cr <= min([plain_1_cr]) and (d[0] == rle_value or rle_len >= 2):
            if d[0] != rle_value:
                # Switch to new rle_value
                e.append((1, array('B', d[0:1])))
                rle_value = d[0]
            # Encode regular RLE
            assert 1 <= rle_len <= MAX_RLE_LENGTH, 'Max RLE encoding wrong'
            if rle_len > MAX_RLE_LENGTH_SHORT:
                rle_len_first_nibble = MAX_RLE_LENGTH_SHORT + 1
            else:
                rle_len_first_nibble = rle_len
            e.append((9 + rle_len_first_nibble - 1, []))
            d, rleinc_base = skip_bytes(d, rleinc_base, rle_len)
            if rle_len > MAX_RLE_LENGTH_SHORT:
                e.append((rle_len - (MAX_RLE_LENGTH_SHORT + 1), []))
        else:
            # Single literal byte
            e.append((0, d[0:1]))
            d, rleinc_base = skip_bytes(d, rleinc_base, 1)
    return encode_bytes(e), rleinc_base
