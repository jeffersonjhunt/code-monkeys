# sixel2png

> Convert DEC SIXEL images into PNG format images

## Synopsis

```
sixel2png -i <input sixel file> -o <output png file>
sixel2png < <input sixel file> > <output png file>
```

## Description

`sixel2png` converts DEC SIXEL images into PNG format images.

## Command-Line Options

| Option | Description |
|--------|-------------|
| `-i` | Specify input file. If omitted or `-`, accepts SIXEL data from STDIN. |
| `-o` | Specify output file. If omitted or `-`, emits PNG data to STDOUT. |

## See Also

- sixel
- img2sixel

## Authors

`sixel2png` is maintained by Hayaki Saito. Includes code from stbiw-0.92 (Sean Barrett) for writing PNG images.

## Thanks

- **stbiw-0.92** — Public domain PNG/BMP/TGA writer: http://nothings.org/stb/stb_image_write.h

## Bugs

Send bug-reports, fixes, enhancements to user@zuse.jp.

## Copyright

Copyright (c) 2014 Hayaki Saito. MIT License.

Source: https://manpages.debian.org/jessie/libsixel-bin/sixel2png.1.en.html
