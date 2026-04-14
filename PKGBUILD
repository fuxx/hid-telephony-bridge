# Maintainer: Stefan Mayer-Popp <stefan@mayer-popp.de>
pkgname=mv7-hid-bridge
pkgver=0.1.0
pkgrel=1
pkgdesc="USB HID Telephony mute bridge for Linux/PipeWire (default: Shure MV7+)"
arch=('any')
url="https://github.com/fuxx/mv7-hid-bridge"
license=('GPL-3.0-only')
depends=('python' 'pipewire-pulse')
source=("$pkgname-$pkgver.tar.gz::$url/archive/refs/tags/v$pkgver.tar.gz")
sha256sums=('SKIP')
install=mv7-hid-bridge.install

package() {
    cd "$pkgname-$pkgver"
    install -Dm755 mv7-hid-bridge.py "$pkgdir/usr/bin/mv7-hid-bridge"
    install -Dm644 99-shure-mv7-hid.rules "$pkgdir/usr/lib/udev/rules.d/99-shure-mv7-hid.rules"
    install -Dm644 mv7-hid-bridge.service "$pkgdir/usr/lib/systemd/user/mv7-hid-bridge.service"
    install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
    install -Dm644 README.md "$pkgdir/usr/share/doc/$pkgname/README.md"
}
