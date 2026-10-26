#!/usr/bin/env bash
# Builds the package jkmons_<version>_<architecture>.deb for Linux Mint / Ubuntu / Debian.
#     bash build_deb.sh
# Install:  sudo apt install ./jkmons_*.deb     Remove:  sudo apt remove jkmons
#
# System dependencies (GTK3, python3-gi, bluez) are installed by apt through the Depends field.
# The bleak and dbus-fast libraries go into the package's private folder (/usr/lib/jkmons/site),
# so they do not conflict with the system Python packages.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

# --- build messages follow the system language (en / uk / ru); usage: m "English" "Українською" "По-русски"
case "${LC_ALL:-${LC_MESSAGES:-${LANG:-en}}}" in
    uk*) _L=2 ;;
    ru*) _L=3 ;;
    *)   _L=1 ;;
esac
m() { eval "printf '%s\n' \"\${$_L}\""; }

PKG=jkmons
VERSION="${VERSION:-1.1.0}"
ARCH="$(dpkg --print-architecture)"
ROOT="build_deb/${PKG}_${VERSION}_${ARCH}"
LIB="$ROOT/usr/lib/$PKG"
OUT="${PKG}_${VERSION}_${ARCH}.deb"
PY=/usr/bin/python3

if [ -z "${SKIP_APT:-}" ]; then
    m "==> 1/4 Build tools (sudo will ask for a password)" "==> 1/4 Інструменти збірки (sudo запитає пароль)" "==> 1/4 Инструменты сборки (sudo спросит пароль)"
    sudo apt-get update -qq
    sudo apt-get install -y python3-pip python3-gi python3-gi-cairo gir1.2-gtk-3.0 bluez dpkg-dev
fi

m "==> 2/4 Package files" "==> 2/4 Файли пакета" "==> 2/4 Файлы пакета"
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
    || { m "Warning: icon sizes were not created, using the 512 px icon only" "Попередження: розміри іконки не створено, кладу лише 512 px" "Предупреждение: размеры иконки не созданы, кладу только 512 px"; \
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
Comment=Bluetooth monitor for JK BMS
Comment[uk]=Bluetooth-монітор для JK BMS
Comment[ru]=Bluetooth-монитор для JK BMS
Exec=$PKG
Icon=$PKG
Categories=Utility;
StartupWMClass=jkmons
Terminal=false
EOF

# sane permissions: files 644, folders and scripts 755 (otherwise a normal user cannot read the icon)
find "$ROOT" -type d -exec chmod 755 {} +
find "$ROOT" -type f -exec chmod 644 {} +
chmod 755 "$ROOT/usr/bin/$PKG"

m "==> 3/4 Package description" "==> 3/4 Опис пакета" "==> 3/4 Описание пакета"
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

# refresh the icon cache and the menu after install/remove (otherwise the menu icon may not appear)
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

m "==> 4/4 Building the .deb" "==> 4/4 Збірка .deb" "==> 4/4 Сборка .deb"
dpkg-deb --root-owner-group --build "$ROOT" "$OUT" >/dev/null
echo
dpkg-deb -I "$OUT" | sed -n '1,12p'
echo
m "Done: $(pwd)/$OUT" "Готово: $(pwd)/$OUT" "Готово: $(pwd)/$OUT"
m "Install: sudo apt install ./$OUT" "Встановлення: sudo apt install ./$OUT" "Установка: sudo apt install ./$OUT"
