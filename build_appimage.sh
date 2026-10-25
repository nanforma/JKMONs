#!/usr/bin/env bash
# Сборка JKMONs-x86_64.AppImage. Запускать на вашем компьютере (Linux Mint / Ubuntu):
#     bash build_appimage.sh
# Нужен интернет и пароль sudo (ставятся пакеты). Занимает около минуты.
#
# Интерфейс GTK3 берётся из системы (python3-gi), в AppImage упаковываются программа и
# библиотеки bleak/dbus-fast. Собранный файл рассчитан на тот же дистрибутив, где он собран.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

PY=/usr/bin/python3
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
OUT="JKMONs-x86_64.AppImage"

echo "==> 1/5 Системные пакеты (спросит пароль sudo)"
sudo apt-get update -qq
sudo apt-get install -y python3-pip python3-gi python3-gi-cairo gir1.2-gtk-3.0 bluez curl
# AppImage для запуска нужен FUSE (в новых системах пакет называется libfuse2t64)
sudo apt-get install -y libfuse2t64 2>/dev/null || sudo apt-get install -y libfuse2 || true

echo "==> 2/5 Python-библиотеки в AppDir"
rm -rf AppDir
mkdir -p AppDir/usr/lib/jkmon/site
"$PY" -m pip install --quiet --target AppDir/usr/lib/jkmon/site --break-system-packages -r requirements.txt \
    || "$PY" -m pip install --quiet --target AppDir/usr/lib/jkmon/site -r requirements.txt
cp jkmon_gtk.py jkcore.py blepair.py i18n.py jkmon.png jkmon.svg AppDir/usr/lib/jkmon/

echo "==> 3/5 Проверка (GTK3 + библиотеки)"
PYTHONPATH="AppDir/usr/lib/jkmon/site:AppDir/usr/lib/jkmon" "$PY" AppDir/usr/lib/jkmon/jkmon_gtk.py --selftest

echo "==> 4/5 Иконка и запускающие файлы"
cp jkmon.png AppDir/jkmons.png
cp jkmon.png AppDir/.DirIcon
cp jkmon.svg AppDir/jkmons.svg
# icon sizes are rendered from the SVG at build time (see make_icons.py)
"$PY" make_icons.py jkmon.svg jkmon.png AppDir/usr/share/icons/hicolor jkmons \
    || echo "Предупреждение: размеры иконки не созданы (останутся jkmons.png и jkmons.svg)"
cat > AppDir/AppRun <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export PYTHONPATH="$HERE/usr/lib/jkmon/site:$HERE/usr/lib/jkmon${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 "$HERE/usr/lib/jkmon/jkmon_gtk.py" "$@"
EOF
chmod +x AppDir/AppRun
cat > AppDir/jkmons.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=JKMONs
Comment=Монитор JK BMS по Bluetooth
Exec=AppRun
Icon=jkmons
Categories=Utility;
StartupWMClass=jkmons
Terminal=false
EOF

echo "==> 5/5 Сборка AppImage"
[ -f appimagetool.AppImage ] || curl -fL --retry 3 -o appimagetool.AppImage "$APPIMAGETOOL_URL"
chmod +x appimagetool.AppImage
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 ./appimagetool.AppImage AppDir "$OUT" >build_appimagetool.log 2>&1 \
    || { echo "Ошибка appimagetool, см. build_appimagetool.log"; exit 1; }
chmod +x "$OUT"

echo
echo "Готово: $(pwd)/$OUT"
echo "Запуск: ./$OUT   (или двойной клик, если включить «Разрешить выполнение» в свойствах файла)"
echo "Без сборки можно запускать так: python3 -m pip install --user --break-system-packages -r requirements.txt && python3 jkmon_gtk.py"
