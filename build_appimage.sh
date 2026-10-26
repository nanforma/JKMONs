#!/usr/bin/env bash
# Builds JKMONs-x86_64.AppImage. Run it on your own computer (Linux Mint / Ubuntu):
#     bash build_appimage.sh
# Needs internet and the sudo password (packages are installed). Takes about a minute.
#
# The GTK3 interface comes from the system (python3-gi); the AppImage contains the program and the
# bleak/dbus-fast libraries. The resulting file is meant for the same distribution it was built on.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

# --- build messages follow the system language (en / uk / ru); usage: m "English" "Українською" "По-русски"
case "${LC_ALL:-${LC_MESSAGES:-${LANG:-en}}}" in
    uk*) _L=2 ;;
    ru*) _L=3 ;;
    *)   _L=1 ;;
esac
m() { eval "printf '%s\n' \"\${$_L}\""; }

PY=/usr/bin/python3
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
OUT="JKMONs-x86_64.AppImage"

m "==> 1/5 System packages (sudo will ask for a password)" "==> 1/5 Системні пакети (sudo запитає пароль)" "==> 1/5 Системные пакеты (sudo спросит пароль)"
sudo apt-get update -qq
sudo apt-get install -y python3-pip python3-gi python3-gi-cairo gir1.2-gtk-3.0 bluez curl
# an AppImage needs FUSE to run (newer systems name the package libfuse2t64)
sudo apt-get install -y libfuse2t64 2>/dev/null || sudo apt-get install -y libfuse2 || true

m "==> 2/5 Python libraries into AppDir" "==> 2/5 Python-бібліотеки в AppDir" "==> 2/5 Python-библиотеки в AppDir"
rm -rf AppDir
mkdir -p AppDir/usr/lib/jkmon/site
"$PY" -m pip install --quiet --target AppDir/usr/lib/jkmon/site --break-system-packages -r requirements.txt \
    || "$PY" -m pip install --quiet --target AppDir/usr/lib/jkmon/site -r requirements.txt
cp jkmon_gtk.py jkcore.py blepair.py i18n.py jkmon.png jkmon.svg AppDir/usr/lib/jkmon/

m "==> 3/5 Check (GTK3 + libraries)" "==> 3/5 Перевірка (GTK3 + бібліотеки)" "==> 3/5 Проверка (GTK3 + библиотеки)"
PYTHONPATH="AppDir/usr/lib/jkmon/site:AppDir/usr/lib/jkmon" "$PY" AppDir/usr/lib/jkmon/jkmon_gtk.py --selftest

m "==> 4/5 Icon and launcher files" "==> 4/5 Іконка та файли запуску" "==> 4/5 Иконка и запускающие файлы"
cp jkmon.png AppDir/jkmons.png
cp jkmon.png AppDir/.DirIcon
cp jkmon.svg AppDir/jkmons.svg
# icon sizes are rendered from the SVG at build time (see make_icons.py)
"$PY" make_icons.py jkmon.svg jkmon.png AppDir/usr/share/icons/hicolor jkmons \
    || m "Warning: icon sizes were not created (only jkmons.png and jkmons.svg remain)" "Попередження: розміри іконки не створено (залишаться jkmons.png і jkmons.svg)" "Предупреждение: размеры иконки не созданы (останутся jkmons.png и jkmons.svg)"
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
Comment=Bluetooth monitor for JK BMS
Comment[uk]=Bluetooth-монітор для JK BMS
Comment[ru]=Bluetooth-монитор для JK BMS
Exec=AppRun
Icon=jkmons
Categories=Utility;
StartupWMClass=jkmons
Terminal=false
EOF

m "==> 5/5 Building the AppImage" "==> 5/5 Збірка AppImage" "==> 5/5 Сборка AppImage"
[ -f appimagetool.AppImage ] || curl -fL --retry 3 -o appimagetool.AppImage "$APPIMAGETOOL_URL"
chmod +x appimagetool.AppImage
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 ./appimagetool.AppImage AppDir "$OUT" >build_appimagetool.log 2>&1 \
    || { m "appimagetool error, see build_appimagetool.log" "Помилка appimagetool, дивіться build_appimagetool.log" "Ошибка appimagetool, см. build_appimagetool.log"; exit 1; }
chmod +x "$OUT"

echo
m "Done: $(pwd)/$OUT" "Готово: $(pwd)/$OUT" "Готово: $(pwd)/$OUT"
m "Run: ./$OUT   (or double-click it after enabling \"Allow executing file as program\" in the file properties)" "Запуск: ./$OUT   (або подвійний клік, якщо ввімкнути «Дозволити виконання» у властивостях файлу)" "Запуск: ./$OUT   (или двойной клик, если включить «Разрешить выполнение» в свойствах файла)"
m "Without building you can run it like this: python3 -m pip install --user --break-system-packages -r requirements.txt && python3 jkmon_gtk.py" "Без збірки можна запускати так: python3 -m pip install --user --break-system-packages -r requirements.txt && python3 jkmon_gtk.py" "Без сборки можно запускать так: python3 -m pip install --user --break-system-packages -r requirements.txt && python3 jkmon_gtk.py"
