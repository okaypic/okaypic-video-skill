"""Download the open fonts the editor burns captions with (SIL Open Font License).

    python fetch_fonts.py [assets_dir]      # default: ./assets

Puts NotoSans-Bold.ttf (Latin) and NotoSansSC-Bold.ttf (Simplified Chinese) in
<assets_dir>/fonts/. You can use any other fonts: point edit.json "fonts" at them.
"""
import os
import sys
import urllib.request

FONTS = {
    "NotoSans-Bold.ttf":
        "https://raw.githubusercontent.com/notofonts/notofonts.github.io/main/fonts/NotoSans/hinted/ttf/NotoSans-Bold.ttf",
    "NotoSansSC-Bold.otf":
        "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/SubsetOTF/SC/NotoSansSC-Bold.otf",
}


def main():
    assets = sys.argv[1] if len(sys.argv) > 1 else "assets"
    d = os.path.join(assets, "fonts")
    os.makedirs(d, exist_ok=True)
    for name, url in FONTS.items():
        dst = os.path.join(d, name)
        if os.path.exists(dst):
            print("have", dst)
            continue
        print("fetching", name, flush=True)
        urllib.request.urlretrieve(url, dst)
        print("saved", dst, os.path.getsize(dst), "bytes")


if __name__ == "__main__":
    main()
