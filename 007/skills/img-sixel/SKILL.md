---
name: img-sixel
description: Display images as SIXEL graphics in the terminal or convert SIXEL files to PNG. Use when asked to show an image inline, render graphics in a terminal, or convert between SIXEL and PNG formats.
license: Apache-2.0
metadata:
  author: ooe
  version: "1.0"
---

# img-sixel

Display images as SIXEL graphics or convert SIXEL to PNG.

## Usage

```bash
# Display an image as SIXEL in the terminal
./scripts/sixel.sh display photo.jpg

# Display with options
./scripts/sixel.sh display -w 320 -p 64 photo.png

# Convert a SIXEL file to PNG
./scripts/sixel.sh convert image.sixel output.png

# Auto-detect: pass a file and it figures out what to do
./scripts/sixel.sh photo.jpg
```

## Dependencies

Requires `libsixel` (`img2sixel` and `sixel2png` commands):

```bash
# macOS
brew install libsixel

# Debian/Ubuntu
apt install libsixel-bin

# Fedora
dnf install libsixel-utils
```
