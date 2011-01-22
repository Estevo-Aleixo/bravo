from numpy import int8, uint8, uint32
from numpy import cast, empty, where, zeros, fromstring

from bravo.blocks import glowing_blocks
from bravo.compat import product
from bravo.entity import tile_entities
from bravo.packets import make_packet
from bravo.serialize import ChunkSerializer
from bravo.utilities import pack_nibbles

# Set up glow tables.
# These tables provide glow maps for illuminated points.
glow = [None] * 15
for i in range(15):
    dim = 2 * i + 1
    glow[i] = zeros((dim, dim, dim), dtype=int8)
    for x, y, z in product(xrange(dim), repeat=3):
        distance = abs(x - i) + abs(y - i) + abs(z - i)
        glow[i][ x,  y,  z] = i + 1 - distance
    glow[i] = cast[uint8](glow[i].clip(0, 15))

def composite_glow(target, strength, x, y, z):
    """
    Composite a light source onto a lightmap.

    The exact operation is not quite unlike an add.
    """

    ambient = glow[strength]

    xbound, zbound, ybound = target.shape

    sx = x - strength
    sy = y - strength
    sz = z - strength

    ex = x + strength
    ey = y + strength
    ez = z + strength

    si, sj, sk = 0, 0, 0
    ei, ej, ek = strength * 2, strength * 2, strength * 2

    if sx < 0:
        sx, si = 0, -sx

    if sy < 0:
        sy, sj = 0, -sy

    if sz < 0:
        sz, sk = 0, -sz

    if ex > xbound:
        ex, ei = xbound, ei - ex + xbound

    if ey > ybound:
        ey, ej = ybound, ej - ey + ybound

    if ez > zbound:
        ez, ek = zbound, ek - ez + zbound

    # Composite!
    target[sx:ex, sz:ez, sy:ey] += ambient[si:ei, sk:ek, sj:ej]

class Chunk(ChunkSerializer):
    """
    A chunk of blocks.

    Chunks are large pieces of world geometry. The blocks, light maps, and
    associated metadata are stored in chunks.
    """

    dirty = True
    """
    Whether this chunk needs to be flushed to disk.
    """

    populated = False
    """
    Whether this chunk has had its initial block data filled out.
    """

    tag = None
    """
    The file backing this chunk.
    """

    known_tile_entities = tile_entities
    """
    Dirty hack to work around mutual recursion during serialization.

    Odds are good that you don't actually want to know why this is necessary.
    Ask me in person if you like, and then you can have some of my brain
    bleach later.
    """

    def __init__(self, x, z):
        """
        Set up the internal data structures for tracking and representing a
        chunk.

        Chunks are large pieces of block data, always measured 16x128x16 and
        aligned on 16x16 boundaries in the xz-plane.

        :param int x: X coordinate in chunk coords
        :param int z: Z coordinate in chunk coords
        """

        self.x = int(x)
        self.z = int(z)

        self.blocks = zeros((16, 16, 128), dtype=uint8)
        self.heightmap = zeros((16, 16), dtype=uint8)
        self.blocklight = zeros((16, 16, 128), dtype=uint8)
        self.metadata = zeros((16, 16, 128), dtype=uint8)
        self.skylight = empty((16, 16, 128), dtype=uint8)
        self.skylight.fill(0xf)

        self.tiles = {}

        self.damaged = zeros((16, 16, 128), dtype=bool)
        """
        Array for tracking damaged coordinates.
        """

        self.all_damaged = False
        """
        Flag for forcing the entire chunk to be damaged.

        This is for efficiency; past a certain point, it is not efficient to
        batch block updates or track damage. Heavily damaged chunks have their
        damage represented as a complete resend of the entire chunk.
        """

    def __repr__(self):
        return "Chunk(%d, %d)" % (self.x, self.z)

    __str__ = __repr__

    def regenerate_heightmap(self):
        """
        Regenerate the height map.

        The height map is merely the position of the tallest block in any
        xz-column.
        """

        for x, z in product(xrange(16), repeat=2):
            for y in range(127, -1, -1):
                if self.blocks[x, z, y]:
                    break

            self.heightmap[x, z] = y

    def regenerate_blocklight(self):
        lightmap = zeros((16, 16, 128), dtype=uint32)

        for x, y, z in product(xrange(16), xrange(128), xrange(16)):
            block = self.blocks[x, z, y]
            if block in glowing_blocks:
                composite_glow(lightmap, glowing_blocks[block], x, y, z)

        self.blocklight = cast[uint8](lightmap.clip(0, 15))

    def regenerate_metadata(self):
        pass

    def regenerate_skylight(self):
        """
        Regenerate the ambient light map.

        Each block's individual light comes from two sources. The ambient
        light comes from the sky.

        The height map must be valid for this method to produce valid results.
        """

        lightmap = zeros((16, 16, 128), dtype=uint32)

        for x, z in product(xrange(16), repeat=2):
            y = self.heightmap[x, z]

            composite_glow(lightmap, 14, x, y, z)

        self.skylight = cast[uint8](lightmap.clip(0, 15))

    def regenerate(self):
        """
        Regenerate all extraneous tables.
        """

        self.regenerate_heightmap()
        self.regenerate_blocklight()
        self.regenerate_metadata()
        self.regenerate_skylight()

        self.dirty = True

    def damage(self, coords):
        """
        Record damage on this chunk.
        """

        x, y, z = coords

        if self.all_damaged:
            return

        self.damaged[x, z, y] = True

        if self.damaged.sum() > 176:
            self.all_damaged = True

    def is_damaged(self):
        """
        Determine whether any damage is pending on this chunk.

        :returns: bool
        """

        return self.all_damaged or self.damaged.any()

    def get_damage_packet(self):
        """
        Make a packet representing the current damage on this chunk.

        This method is not private, but some care should be taken with it,
        since it wraps some fairly cryptic internal data structures.

        If this chunk is currently undamaged, this method will return an empty
        string, which should be safe to treat as a packet. Please check with
        `is_damaged()` before doing this if you need to optimize this case.

        To avoid extra overhead, this method should really be used in
        conjunction with `Factory.broadcast_for_chunk()`.

        Do not forget to clear this chunk's damage! Callers are responsible
        for doing this.

        >>> packet = chunk.get_damage_packet()
        >>> factory.broadcast_for_chunk(packet, chunk.x, chunk.z)
        >>> chunk.clear_damage()

        :returns: str representing a packet
        """

        if self.all_damaged:
            # Resend the entire chunk!
            return self.save_to_packet()
        elif not self.damaged.any():
            return ""
        elif self.damaged.sum() == 1:
            # Use a single block update packet.
            x, z, y = [int(i) for i in zip(*self.damaged.nonzero())[0]]
            return make_packet("block",
                    x=x + self.x * 16,
                    y=y,
                    z=z + self.x * 16,
                    type=int(self.blocks[x, z, y]),
                    meta=int(self.metadata[x, z, y]))
        else:
            # Use a batch update.
            damaged = self.damaged.nonzero()
            # Coordinates are not quite packed in the same system as the
            # indices for chunk data structures.
            # Chunk data structures are ((x * 16) + z) * 128) + y, or in
            # bit-twiddler's parlance, x << 11 | z << 7 | y. However, for
            # this, we need x << 12 | z << 8 | y, so repack accordingly.
            coords = [int(x << 12 | z << 8 | y) for x, z, y in zip(*damaged)]
            types = [int(i) for i in self.blocks[damaged]]
            metadata = [int(i) for i in self.metadata[damaged]]

            return make_packet("batch", x=self.x, z=self.z,
                length=len(coords), coords=coords, types=types,
                metadata=metadata)

    def clear_damage(self):
        """
        Clear this chunk's damage.
        """

        self.damaged.fill(False)
        self.all_damaged = False

    def save_to_packet(self):
        """
        Generate a chunk packet.
        """

        array = self.blocks.tostring()
        array += pack_nibbles(self.metadata)
        array += pack_nibbles(self.skylight)
        array += pack_nibbles(self.blocklight)
        packet = make_packet("chunk", x=self.x * 16, y=0, z=self.z * 16,
            x_size=15, y_size=127, z_size=15, data=array)
        return packet

    def load_from_packet(self, packet):
        cx, bx = divmod(packet.x, 16)
        cz, bz = divmod(packet.z, 16)

        if (cx != self.x) or (cz != self.z):
            print "loading packet data in wrong chunk location"
            print cx, cz, self.x, self.z
            return

        # server always sends the size - 1
        x_size = packet.x_size + 1
        y_size = packet.y_size + 1
        z_size = packet.z_size + 1

        # index for reading the packet data
        p_index = x_size * z_size * y_size

        # index for modifying the chunk
        #c_index = packet.y + (bz * y_size) + (bx * y_size * z_size)

        # im sure there is a faster operation in numpy than this
        # and by this i mean, the rest of this function
        data = fromstring(packet.data, dtype=uint8)
       
        x = bx
        z = bz
        y = packet.y

        sky_index = p_index + p_index / 2
        light_index = p_index * 2

        x_size -= 1
        z_size -= 1
        y_size -= 1

        for i in xrange(p_index):
            #print x, z, y, x_size, z_size, y_size
            self.blocks[x, z, y] = data[i]

            # the remaining data is packed as nibbles
            # so don't advance as quickly as i
            i2 = i / 2

            # track if we should use the nibble given to us
            # or to use the one in the buffer
            nibble = i % 2

            # metadata, skylight, and blocklight all are packed
            if nibble:
                self.metadata[x,z,y] = meta_pb
                #self.skylight[x,z,y] = sky_pb
                #self.blocklight[x,z,y] = light_pb
            else:
                m = data[i2 + p_index]
                self.metadata[x,z,y] = m >> 4
                meta_pb = m & 15

                #s = data[i2 + sky_index]
                #self.skylight[x,z,y] = s >> 4
                #sky_pb = s & 15

                #l = data[i2 + light_index]
                #self.blocklight[x,z,y] = l >> 4
                #light_pb = l & 15

            y += 1
            if y > y_size:
                z += 1
                y = 0
            if z > z_size:
                x += 1
                z = 0

    def get_block(self, coords):
        """
        Look up a block value.

        :param tuple coords: coordinate triplet

        :returns: int representing block type
        """

        x, y, z = coords

        return self.blocks[x, z, y]

    def set_block(self, coords, block):
        """
        Update a block value.

        :param tuple coords: coordinate triplet
        :param int block: block type
        """

        x, y, z = coords

        if self.blocks[x, z, y] != block:
            self.blocks[x, z, y] = block

            # Regenerate heightmap at this coordinate. Honestly not sure
            # whether or not this is cheaper than the set of conditional
            # statements required to update it in relative terms instead of
            # absolute terms. Revisit this later, maybe?
            # XXX definitely re-examine this later!
            for y in range(127, -1, -1):
                if self.blocks[x, z, y]:
                    break
            self.heightmap[x, z] = y

            # Add to lightmap at this coordinate.
            if block in glowing_blocks:
                composite_glow(self.blocklight, glowing_blocks[block], x, y, z)

                self.blocklight = cast[uint8](self.blocklight.clip(0, 15))

            self.dirty = True
            self.damage(coords)

    def get_metadata(self, coords):
        """
        Look up metadata.

        :param tuple coords: coordinate triplet

        :returns: int
        """

        x, y, z = coords

        return self.metadata[x, z, y]

    def set_metadata(self, coords, metadata):
        """
        Update metadata.

        :param tuple coords: coordinate triplet
        :param int metadata:
        """

        x, y, z = coords

        if self.metadata[x, z, y] != metadata:
            self.metadata[x, z, y] = metadata

            self.dirty = True
            self.damage(coords)

    def height_at(self, x, z):
        """
        Get the height of an xz-column of blocks.

        :param int x: X coordinate
        :param int z: Z coordinate
        :returns: int representing height
        """

        return self.heightmap[x, z]

    def sed(self, search, replace):
        """
        Execute a search and replace on all blocks in this chunk.

        Named after the ubiquitous Unix tool. Does a semantic
        s/search/replace/g on this chunk's blocks.

        :param int search: block to find
        :param int replace: block to use as a replacement
        """

        if (self.blocks == search).any():
            self.all_damaged = True
            self.dirty = True

            self.blocks = where(self.blocks == search, replace, self.blocks)

    def get_column(self, x, z):
        """
        Return a slice of the block data at the given xz-column.

        The slice is a numpy array, so you do not have to set it again if you
        are modifying it in-place.
        """

        return self.blocks[x, z]

    def set_column(self, x, z, column):
        """
        Atomically set an entire xz-column's block data.
        """

        self.blocks[x, z] = column

        self.dirty = True
        for y in range(128):
            self.damage((x, y, z))
