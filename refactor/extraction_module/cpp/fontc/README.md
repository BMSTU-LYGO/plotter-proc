# fontc

Isolated C++20 rewrite of the offline centerline-font compiler.

```sh
cmake -S . -B build
cmake --build build
./build/fontc assets/1.ttf --chars-file assets/font-cache-corpus.txt --output font-cache/1/font.pfc
```

FreeType is the only external production dependency. The implementation is
kept outside the current Python runtime until the regression gate is met.
