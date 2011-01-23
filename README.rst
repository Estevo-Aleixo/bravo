==================
Bravo - Client Mod
==================

Server
------
Bravo is a elegant, speedy, and extensible implementation of the Minecraft
Alpha/Beta protocol. Only the server side is implemented. Bravo also has a few
tools useful for examining the wire protocols and disk formats in Minecraft.

ClientMod
---------
Making changes here/there from the official repo so that Bravo can be used
as a library for a client.  Main changes are to enable decoding of packets
into objects used by bravo.


Installing
==========

Bravo ships with a standard setup.py. You will need setuptools/distribute, but
most distributions already provide it for you. Bravo depends on the following
external libraries from PyPI:

 * construct or reconstruct
 * numpy
 * Twisted

Bravo also uses the external NBT library (http://github.com/twoolie/NBT) for
reading and saving MC Alpha worlds. Since this library is in flux, a version
that works with Bravo has been bundled.

We highly recommend pip for installing Bravo, since it handles all dependencies
for you.

::

 $ pip install Bravo

Bravo can also optionally use Ampoule to offload some of its inner
calculations to a separate process, improving server response times. Ampoule
will be automatically detected and is completely optional.

::

 $ pip install ampoule


License
=======

Bravo is made available under the following terms, commonly known as the
MIT/X11 license. Contributions from third parties are also under this license.

Copyright (c) 2010 Corbin Simpson et al.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
