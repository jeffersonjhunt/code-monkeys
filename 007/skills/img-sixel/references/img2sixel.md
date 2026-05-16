# img2sixel

> Image converter to DEC SIXEL graphics

## Synopsis

```
img2sixel [-options] imagefiles
img2sixel [-options] < imagefiles
```

## Description

`img2sixel` converts JPEG/PNG images into DEC SIXEL image format.

## Command-Line Options

| Option | Description |
|--------|-------------|
| `-7`, `--7bit-mode` | Generate a sixel image for 7bit terminals or printers (default). |
| `-8`, `--8bit-mode` | Generate a sixel image for 8bit terminals or printers. |
| `-p COLORS`, `--colors=COLORS` | Specify number of colors to reduce the image to (default=256). |
| `-m FILE`, `--mapfile=FILE` | Transform image colors to match this set of colors. |
| `-e`, `--monochrome` | Output monochrome sixel image. Assumes the terminal background color is black. |
| `-i`, `--invert` | Assume the terminal background color is white. Makes sense only with `-e`. |
| `-u`, `--use-macro` | Use DECDMAC and DEVINVM sequences to optimize GIF animation rendering. |
| `-g`, `--ignore-delay` | Render GIF animation without delay. |

### `-d DIFFUSIONTYPE`, `--diffusion=DIFFUSIONTYPE`

Choose diffusion method used with color reduction.

| Type | Description |
|------|-------------|
| `auto` | Choose diffusion type automatically (default) |
| `none` | Do not diffuse |
| `fs` | Floyd-Steinberg method |
| `atkinson` | Bill Atkinson's method |
| `jajuni` | Jarvis, Judice & Ninke |
| `stucki` | Stucki's method |
| `burkes` | Burkes' method |

### `-f FINDTYPE`, `--find-largest=FINDTYPE`

Choose method for finding the largest dimension of median cut boxes for splitting. Makes sense only when `-p` option (color reduction) is specified.

| Type | Description |
|------|-------------|
| `auto` | Choose finding method automatically (default) |
| `norm` | Simply comparing the range in RGB space |
| `lum` | Transforming into luminosities before the comparison |

### `-s SELECTTYPE`, `--select-color=SELECTTYPE`

Choose the method for selecting representative color from each median-cut box. Makes sense only when `-p` option (color reduction) is specified.

| Type | Description |
|------|-------------|
| `auto` | Choose selecting method automatically (default) |
| `center` | Choose the center of the box |
| `average` | Calculate the color average into the box |
| `histgram` | Similar to average but considers color histogram |

### `-c REGION`, `--crop=REGION`

Crop source image to fit the specified geometry. REGION should be formatted as `%dx%d+%d+%d`.

### `-w WIDTH`, `--width=WIDTH`

Resize image to specified width.

| Syntax | Description |
|--------|-------------|
| `auto` | Preserving aspect ratio (default) |
| `<number>%` | Scale width with given percentage |
| `<number>` | Scale width with pixel counts |
| `<number>px` | Scale width with pixel counts |

### `-h HEIGHT`, `--height=HEIGHT`

Resize image to specified height.

| Syntax | Description |
|--------|-------------|
| `auto` | Preserving aspect ratio (default) |
| `<number>%` | Scale height with given percentage |
| `<number>` | Scale height with pixel counts |
| `<number>px` | Scale height with pixel counts |

### `-r RESAMPLINGTYPE`, `--resampling=RESAMPLINGTYPE`

Choose resampling method used with `-w` or `-h` option (scaling).

| Type | Description |
|------|-------------|
| `nearest` | Nearest-Neighbor method |
| `gaussian` | Gaussian filter |
| `hanning` | Hanning filter |
| `hamming` | Hamming filter |
| `bilinear` | Bilinear filter (default) |
| `welsh` | Welsh filter |
| `bicubic` | Bicubic filter |
| `lanczos2` | Lanczos-2 filter |
| `lanczos3` | Lanczos-3 filter |
| `lanczos4` | Lanczos-4 filter |

### `-q QUALITYMODE`, `--quality=QUALITYMODE`

Select quality of color quantization.

| Mode | Description |
|------|-------------|
| `auto` | Decide quality mode automatically (default) |
| `high` | High quality and low speed mode |
| `low` | Low quality and high speed mode |

### `-l LOOPMODE`, `--loop-control=LOOPMODE`

Select loop control mode for GIF animation.

| Mode | Description |
|------|-------------|
| `auto` | Honor the setting of GIF header (default) |
| `force` | Always enable loop |
| `disable` | Always disable loop |

## See Also

- sixel
- sixel2png

## Authors

`img2sixel` is maintained by Hayaki Saito. Includes code from stbi-1.41 (Sean Barrett) for loading PNG/JPEG images, and code from pnmquant.c (netpbm library) for image quantization.

## Copyright

Copyright (c) 2014 Hayaki Saito. MIT License.

Source: https://manpages.debian.org/jessie/libsixel-bin/img2sixel.1
