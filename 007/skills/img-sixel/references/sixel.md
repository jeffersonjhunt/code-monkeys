# sixel

> SIXEL bitmap graphics format

## Description

SIXEL is a bitmap graphics format for terminals and printers introduced by Digital Equipment Corp. (DEC). Its data scheme is represented as a terminal-friendly escape sequence. To display a SIXEL image file, simply `cat` it to your terminal.

## Terminal Requirements

- DEC VT series: VT240/VT241/VT330/VT340/VT282/VT284/VT286/VT382
- RLogin (Japanese terminal emulator)
- tanasinn (Works with Firefox)
- mlterm (Works on X, win32/cygwin, and framebuffer)
- XTerm (configured with `--enable-sixel-graphics`, launched with `-ti 340`)
- yaft / yaftx (Works on framebuffer / X11)
- DECterm
- Kermit for DOS
- WRQ Reflection
- ZSTEM

## See Also

- img2sixel
- sixel2png

## References

- [All About SIXELs](ftp://ftp.cs.utk.edu/pub/shuford/terminal/all_about_sixels.txt) (Sep 29, 1990)
- [Displaying Sixel Image Files](http://rullf2.xs4all.nl/sg/doc.html) (2014)

## Source

https://manpage.me/index.cgi?q=sixel&sektion=5&apropos=0&manpath=FreeBSD+11.1-RELEASE+and+Ports
