#!/usr/bin/env bash
# Сборка пакета jkmons_<версия>_<архитектура>.deb для Linux Mint / Ubuntu / Debian.
#     bash build_deb.sh
# Установка:  sudo apt install ./jkmons_*.deb     Удаление:  sudo apt remove jkmons
#
# Системные зависимости (GTK3, python3-gi, bluez) apt ставит сам по полю Depends.
# Библиотеки bleak и dbus-fast кладутся в приватную папку пакета (/usr/lib/jkmons/site),
# поэтому они не конфликтуют с системными пакетами Python.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

PKG=jkmons
VERSION="${VERSION:-1.1.0}"
ARCH="$(dpkg --print-architecture)"
ROOT="build_deb/${PKG}_${VERSION}_${ARCH}"
LIB="$ROOT/usr/lib/$PKG"
OUT="${PKG}_${VERSION}_${ARCH}.deb"
PY=/usr/bin/python3

if [ -z "${SKIP_APT:-}" ]; then
    echo "==> 1/4 Инструменты сборки (спросит пароль sudo)"
    sudo apt-get update -qq
    sudo apt-get install -y python3-pip python3-gi python3-gi-cairo gir1.2-gtk-3.0 bluez dpkg-dev
fi

echo "==> 2/4 Файлы пакета"
rm -rf build_deb
mkdir -p "$LIB/site" "$ROOT/DEBIAN" "$ROOT/usr/bin" "$ROOT/usr/share/applications" \
         "$ROOT/usr/share/pixmaps" "$ROOT/usr/share/icons/hicolor/scalable/apps"
if [ -z "${SKIP_PIP:-}" ]; then
    "$PY" -m pip install --quiet --target "$LIB/site" --break-system-packages -r requirements.txt \
        || "$PY" -m pip install --quiet --target "$LIB/site" -r requirements.txt
fi
cp jkmon_gtk.py jkcore.py blepair.py i18n.py jkmon.png jkmon.svg "$LIB/"
cp jkmon.png "$ROOT/usr/share/pixmaps/$PKG.png"
# icon sizes for the menu / panel are rendered from the SVG at build time (see make_icons.py)
"$PY" make_icons.py jkmon.svg jkmon.png "$ROOT/usr/share/icons/hicolor" "$PKG" \
    || { echo "Предупреждение: размеры иконки не созданы, кладу только 512 px"; \
         mkdir -p "$ROOT/usr/share/icons/hicolor/512x512/apps"; \
         cp jkmon.png "$ROOT/usr/share/icons/hicolor/512x512/apps/$PKG.png"; }
find "$LIB" -name '__pycache__' -type d -prune -exec rm -rf {} +

cat > "$ROOT/usr/bin/$PKG" <<'EOF'
#!/bin/sh
export PYTHONPATH="/usr/lib/jkmons/site:/usr/lib/jkmons${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 /usr/lib/jkmons/jkmon_gtk.py "$@"
EOF
chmod 755 "$ROOT/usr/bin/$PKG"

cat > "$ROOT/usr/share/applications/$PKG.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=JKMONs
Comment=Монитор JK BMS по Bluetooth
Exec=$PKG
Icon=$PKG
Categories=Utility;
StartupWMClass=jkmons
Terminal=false
EOF

# нормальные права: файлы 644, папки и скрипты 755 (иначе обычный пользователь не прочитает иконку)
find "$ROOT" -type d -exec chmod 755 {} +
find "$ROOT" -type f -exec chmod 644 {} +
chmod 755 "$ROOT/usr/bin/$PKG"

echo "==> 3/4 Описание пакета"
SIZE=$(du -sk "$ROOT/usr" | cut -f1)
cat > "$ROOT/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Installed-Size: $SIZE
Depends: python3 (>= 3.10), python3-gi, python3-gi-cairo, gir1.2-gtk-3.0, bluez
Maintainer: JKMONs <user@localhost>
Description: JKMONs - Bluetooth monitor for JK BMS (GTK3)
 Read-only monitor for JK BMS (protocol JK02_32S): cell voltages, current,
 SOC, temperatures, balancing state and a load bar with the time left to full charge or empty.
EOF

# обновление кэша иконок и меню после установки/удаления (иначе значок в меню может не появиться)
for script in postinst postrm; do
    cat > "$ROOT/DEBIAN/$script" <<'EOS'
#!/bin/sh
set -e
if [ -x /usr/bin/gtk-update-icon-cache ]; then
    gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor || true
fi
if [ -x /usr/bin/update-desktop-database ]; then
    update-desktop-database -q /usr/share/applications || true
fi
exit 0
EOS
    chmod 755 "$ROOT/DEBIAN/$script"
done

echo "==> 4/4 Сборка .deb"
dpkg-deb --root-owner-group --build "$ROOT" "$OUT" >/dev/null
echo
dpkg-deb -I "$OUT" | sed -n '1,12p'
echo
echo "Готово: $(pwd)/$OUT"
echo "Установка: sudo apt install ./$OUT"
