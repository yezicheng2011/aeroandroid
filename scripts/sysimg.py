"""Read files out of an Android emulator system image with nothing but the standard library.

An emulator `system.img` is a GPT disk holding a `super` partition. `super` is Android's dynamic-partition
container (liblp) and holds ext4 filesystems such as `system`. macOS ships no tool that can open these, so this
module reads just enough of both formats, read-only, to copy files out:

    with open('system.img', 'rb') as image:
        super_offset = gpt_partitions(image)['super'][0]
        system = Ext4(lp_partition(image, super_offset, 'system'))
        system.extract('/system/lib64/libndk_translation.so', Path('out/libndk_translation.so'))
"""
from __future__ import annotations
import os
from pathlib import Path
import stat
import struct

SECTOR = 512
EXT4_MAGIC = 0xEF53
EXTENTS_FL = 0x80000
INCOMPAT_64BIT = 0x80


class ImageError(Exception):
    pass


def gpt_partitions(f):
    """{name: (byte offset, byte size)} from a GPT disk image."""
    f.seek(SECTOR)
    header = f.read(92)
    if header[:8] != b'EFI PART':
        raise ImageError('Not a GPT disk image')
    entries_lba, count, size = struct.unpack('<QII', header[72:88])
    f.seek(entries_lba * SECTOR)
    found = {}
    for _ in range(count):
        entry = f.read(size)
        if entry[:16] == bytes(16):
            continue
        first, last = struct.unpack('<QQ', entry[32:48])
        name = entry[56:128].decode('utf-16le').rstrip('\0')
        found[name] = (first * SECTOR, (last - first + 1) * SECTOR)
    return found


class Extents:
    """A partition stored as linear extents of a bigger file: read_at() hides the gaps."""

    def __init__(self, f, extents):
        self.f = f
        self.extents = []      # (start in partition, length, offset in file)
        position = 0
        for length, offset in extents:
            self.extents.append((position, length, offset))
            position += length
        self.size = position

    def read_at(self, position, count):
        end = min(position + count, self.size)
        out = bytearray()
        for start, length, offset in self.extents:
            low, high = max(position, start), min(end, start + length)
            if low < high:
                self.f.seek(offset + (low - start))
                out += self.f.read(high - low)
        return bytes(out)


def lp_partitions(f, super_offset):
    """{name: [(length in bytes, offset in file)]} for the logical partitions inside `super`."""
    f.seek(super_offset + 4096)
    geometry = f.read(52)
    if struct.unpack('<I', geometry[:4])[0] != 0x616C4467:
        raise ImageError('No Android dynamic-partition geometry found')
    f.seek(super_offset + 12288)
    header = f.read(256)
    if struct.unpack('<I', header[:4])[0] != 0x414C5030:
        raise ImageError('No Android dynamic-partition metadata found')
    header_size = struct.unpack('<I', header[8:12])[0]
    tables = struct.unpack('<12I', header[80:128])   # partitions, extents, groups, block devices: offset, count, size
    base = super_offset + 12288 + header_size

    def table(index):
        offset, count, size = tables[index * 3:index * 3 + 3]
        f.seek(base + offset)
        return [f.read(size) for _ in range(count)]

    extents = table(1)
    result = {}
    for entry in table(0):
        name = entry[:36].split(b'\0')[0].decode()
        _attributes, first, count, _group = struct.unpack('<IIII', entry[36:52])
        pieces = []
        for raw in extents[first:first + count]:
            sectors, kind, data, _source = struct.unpack('<QIQI', raw)
            if kind != 0:
                raise ImageError('Unsupported dynamic-partition extent')
            pieces.append((sectors * SECTOR, super_offset + data * SECTOR))
        result[name] = pieces
    return result


def lp_partition(f, super_offset, name):
    parts = lp_partitions(f, super_offset)
    if name not in parts:
        raise ImageError(f'No partition named {name}; found {sorted(parts)}')
    return Extents(f, parts[name])


class Ext4:
    """Read-only ext4: enough to walk directories and copy files and symlinks."""

    def __init__(self, source):
        self.source = source
        sb = source.read_at(1024, 1024)
        if struct.unpack('<H', sb[56:58])[0] != EXT4_MAGIC:
            raise ImageError('Not an ext4 filesystem')
        self.block_size = 1024 << struct.unpack('<I', sb[24:28])[0]
        self.inodes_per_group = struct.unpack('<I', sb[40:44])[0]
        self.inode_size = struct.unpack('<H', sb[88:90])[0]
        incompat = struct.unpack('<I', sb[96:100])[0]
        self.desc_size = struct.unpack('<H', sb[254:256])[0] if incompat & INCOMPAT_64BIT else 32
        first_data_block = struct.unpack('<I', sb[20:24])[0]
        blocks_lo = struct.unpack('<I', sb[4:8])[0]
        blocks_hi = struct.unpack('<I', sb[336:340])[0] if incompat & INCOMPAT_64BIT else 0
        blocks = blocks_lo | blocks_hi << 32
        per_group = struct.unpack('<I', sb[32:36])[0]
        groups = -(-(blocks - first_data_block) // per_group)
        table = source.read_at((first_data_block + 1) * self.block_size, groups * self.desc_size)
        self.inode_tables = []
        for group in range(groups):
            d = table[group * self.desc_size:(group + 1) * self.desc_size]
            low = struct.unpack('<I', d[8:12])[0]
            high = struct.unpack('<I', d[40:44])[0] if self.desc_size >= 64 else 0
            self.inode_tables.append(low | high << 32)

    def inode(self, number):
        group, index = divmod(number - 1, self.inodes_per_group)
        raw = self.source.read_at(self.inode_tables[group] * self.block_size + index * self.inode_size, 128)
        mode = struct.unpack('<H', raw[0:2])[0]
        flags = struct.unpack('<I', raw[32:36])[0]
        size = struct.unpack('<I', raw[4:8])[0] | struct.unpack('<I', raw[108:112])[0] << 32
        return {'mode': mode, 'size': size, 'flags': flags, 'block': raw[40:100]}

    def _extent_blocks(self, node):
        magic, entries, _max, depth = struct.unpack('<HHHH', node[:8])
        if magic != 0xF30A:
            raise ImageError('Bad extent tree')
        for i in range(entries):
            e = node[12 + i * 12:24 + i * 12]
            if depth == 0:
                logical, length, high, low = struct.unpack('<IHHI', e)
                if length > 32768:      # uninitialised extent: reads as zeros
                    continue
                yield logical, length, high << 32 | low
            else:
                _logical, low, high = struct.unpack('<IIH', e[:10])
                child = self.source.read_at((high << 32 | low) * self.block_size, self.block_size)
                yield from self._extent_blocks(child)

    def read(self, number):
        node = self.inode(number)
        size = node['size']
        if stat.S_ISLNK(node['mode']) and size < 60 and not node['flags'] & EXTENTS_FL:
            return node['block'][:size]
        if not node['flags'] & EXTENTS_FL:
            raise ImageError('Only extent-mapped files are supported')
        data = bytearray(size)
        for logical, length, physical in self._extent_blocks(node['block']):
            start = logical * self.block_size
            if start >= size:
                continue
            take = min(length * self.block_size, size - start)
            data[start:start + take] = self.source.read_at(physical * self.block_size, take)
        return bytes(data)

    def listdir(self, number):
        """{name: (inode, mode)} of a directory."""
        data = self.read(number)
        found = {}
        position = 0
        while position + 8 <= len(data):
            child, record, name_length = struct.unpack('<IHB', data[position:position + 7])
            if record < 8:
                break
            if child and name_length:
                name = data[position + 8:position + 8 + name_length].decode('utf-8', 'replace')
                if name not in ('.', '..'):
                    found[name] = (child, self.inode(child)['mode'])
            position += record
        return found

    def lookup(self, path):
        number = 2
        for part in [p for p in path.split('/') if p]:
            entries = self.listdir(number)
            if part not in entries:
                raise ImageError(f'No such file: {path}')
            number = entries[part][0]
            if stat.S_ISLNK(entries[part][1]):
                raise ImageError(f'Refusing to follow a symlink inside {path}')
        return number

    def walk(self, path):
        """Yield (path, inode, mode) for everything below a directory."""
        stack = [(path.rstrip('/') or '/', self.lookup(path))]
        while stack:
            where, number = stack.pop()
            for name, (child, mode) in sorted(self.listdir(number).items()):
                full = f"{where.rstrip('/')}/{name}"
                yield full, child, mode
                if stat.S_ISDIR(mode):
                    stack.append((full, child))

    def extract(self, path, destination):
        """Copy a file or a whole directory tree. Executable bits are kept; symlinks stay symlinks."""
        number = self.lookup(path)
        mode = self.inode(number)['mode']
        if not stat.S_ISDIR(mode):
            self._copy(number, mode, Path(destination))
            return
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        base = path.rstrip('/')
        for full, child, child_mode in self.walk(path):
            self._copy(child, child_mode, destination / full[len(base) + 1:])

    def _copy(self, number, mode, target):
        if stat.S_ISDIR(mode):
            target.mkdir(parents=True, exist_ok=True)
        elif stat.S_ISLNK(mode):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.unlink(missing_ok=True)
            os.symlink(self.read(number).decode(), target)
        elif stat.S_ISREG(mode):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.read(number))
            target.chmod(mode & 0o777)
