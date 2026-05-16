#!/usr/bin/env bash
# sixel.sh — Display images as SIXEL or convert SIXEL to PNG
#
# Dependencies:
#   img2sixel  (libsixel-bin) — converts images to SIXEL format
#   sixel2png  (libsixel-bin) — converts SIXEL data to PNG
#
# Install:
#   macOS:   brew install libsixel
#   Debian:  apt install libsixel-bin
#   Fedora:  dnf install libsixel-utils
#
# Usage:
#   sixel.sh display <image>           Display image as SIXEL in terminal
#   sixel.sh convert <sixel> [output]  Convert SIXEL file to PNG
#   sixel.sh help                      Show this help
#
# Options (display mode):
#   -w, --width WIDTH       Resize width (pixels, percentage, or "auto")
#   -h, --height HEIGHT     Resize height (pixels, percentage, or "auto")
#   -p, --colors COLORS     Max colors (default: 256)
#   -d, --diffusion TYPE    Dithering: auto|none|fs|atkinson|jajuni|stucki|burkes
#   -e, --monochrome        Output monochrome
#   -8, --8bit              Use 8-bit mode
#   -o, --output FILE       Save SIXEL output to file instead of terminal
#
# Options (convert mode):
#   -o, --output FILE       Output PNG path (default: <input>.png)

set -euo pipefail

die() { echo "Error: $*" >&2; exit 1; }

check_deps() {
    local missing=()
    command -v img2sixel >/dev/null 2>&1 || missing+=(img2sixel)
    command -v sixel2png >/dev/null 2>&1 || missing+=(sixel2png)
    if [[ ${#missing[@]} -gt 0 ]]; then
        die "Missing dependencies: ${missing[*]}
Install with:
  macOS:   brew install libsixel
  Debian:  apt install libsixel-bin
  Fedora:  dnf install libsixel-utils"
    fi
}

usage() {
    sed -n '2,/^[^#]/s/^# \{0,1\}//p' "$0"
    exit 0
}

cmd_display() {
    local opts=()
    local file=""
    local output=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -w|--width)   opts+=(--width="$2"); shift 2 ;;
            -h|--height)  opts+=(--height="$2"); shift 2 ;;
            -p|--colors)  opts+=(--colors="$2"); shift 2 ;;
            -d|--diffusion) opts+=(--diffusion="$2"); shift 2 ;;
            -e|--monochrome) opts+=(--monochrome); shift ;;
            -8|--8bit)    opts+=(--8bit-mode); shift ;;
            -o|--output)  output="$2"; shift 2 ;;
            -*)           die "Unknown option: $1" ;;
            *)            file="$1"; shift ;;
        esac
    done

    [[ -z "$file" ]] && die "No image file specified.
Usage: sixel.sh display <image>"

    [[ -f "$file" ]] || die "File not found: $file"

    if [[ -n "$output" ]]; then
        img2sixel "${opts[@]+"${opts[@]}"}" "$file" > "$output"
        echo "$output"
    else
        img2sixel "${opts[@]+"${opts[@]}"}" "$file"
    fi
}

cmd_convert() {
    local input="" output=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -o|--output) output="$2"; shift 2 ;;
            -*)          die "Unknown option: $1" ;;
            *)
                if [[ -z "$input" ]]; then
                    input="$1"
                elif [[ -z "$output" ]]; then
                    output="$1"
                fi
                shift ;;
        esac
    done

    [[ -z "$input" ]] && die "No input file specified.
Usage: sixel.sh convert <sixel-file> [output.png]"

    [[ -f "$input" ]] || die "File not found: $input"

    [[ -z "$output" ]] && output="${input%.*}.png"

    sixel2png -i "$input" -o "$output"
    echo "$output"
}

# --- Main ---

[[ $# -eq 0 ]] && usage

case "${1:-}" in
    help|--help|-h) usage ;;
esac

check_deps

case "${1:-}" in
    display) shift; cmd_display "$@" ;;
    convert) shift; cmd_convert "$@" ;;
    *)
        # Default: if file looks like sixel, convert; otherwise display
        if [[ -f "$1" ]]; then
            if head -c 10 "$1" | grep -q $'\x1bP\|DCS'; then
                cmd_convert "$@"
            else
                cmd_display "$@"
            fi
        else
            die "Unknown command or file not found: $1
Usage: sixel.sh [display|convert|help] ..."
        fi
        ;;
esac
