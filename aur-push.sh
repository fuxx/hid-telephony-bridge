#!/bin/bash
set -euo pipefail

# Push PKGBUILD to AUR after local verification.
#
# Usage:
#   ./aur-push.sh v0.1.0
#
# Prerequisites:
#   - AUR account with SSH key: https://aur.archlinux.org
#   - Package registered: ssh aur@aur.archlinux.org setup-repo mv7-hid-bridge
#
# Workflow:
#   1. Tag and push to GitHub (triggers CI build)
#   2. Download CI checksums.txt from the GitHub Actions artifacts
#   3. Run this script — it builds locally and compares checksums
#   4. Review the diff, then confirm the push to AUR

AUR_REPO="ssh://aur@aur.archlinux.org/mv7-hid-bridge.git"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <tag>  (e.g. v0.1.0)"
    exit 1
fi

TAG="$1"
VERSION="${TAG#v}"

echo "=== AUR Push: mv7-hid-bridge $VERSION ==="
echo

# Step 1: Verify the tag exists locally
if ! git rev-parse "$TAG" &>/dev/null; then
    echo "ERROR: Tag $TAG not found. Create it first:"
    echo "  git tag $TAG && git push origin $TAG"
    exit 1
fi

# Step 2: Download source tarball and compute checksum
echo "[1/5] Downloading source tarball..."
TARBALL_URL="https://github.com/fuxx/mv7-hid-bridge/archive/refs/tags/${TAG}.tar.gz"
TARBALL="mv7-hid-bridge-${VERSION}.tar.gz"
curl -sL "$TARBALL_URL" -o "/tmp/$TARBALL"
LOCAL_SHA256=$(sha256sum "/tmp/$TARBALL" | cut -d' ' -f1)
echo "      Source tarball SHA256: $LOCAL_SHA256"

# Step 3: Check against CI checksums if available
CI_CHECKSUMS="$SCRIPT_DIR/checksums.txt"
if [[ -f "$CI_CHECKSUMS" ]]; then
    CI_SHA256=$(grep '^source_tarball_sha256=' "$CI_CHECKSUMS" | cut -d= -f2)
    if [[ "$LOCAL_SHA256" == "$CI_SHA256" ]]; then
        echo "      CI checksum match: OK"
    else
        echo ""
        echo "ERROR: Source tarball checksum mismatch!"
        echo "  Local: $LOCAL_SHA256"
        echo "  CI:    $CI_SHA256"
        echo ""
        echo "This could indicate the tarball was modified after CI built it."
        echo "Investigate before proceeding."
        exit 1
    fi
else
    echo "      WARNING: No checksums.txt found. Download it from the GitHub"
    echo "      Actions artifacts to verify against the CI build."
    echo ""
    read -rp "Continue without CI verification? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || exit 1
fi

# Step 4: Prepare PKGBUILD with real version and checksum
echo "[2/5] Preparing PKGBUILD..."
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

cp "$SCRIPT_DIR/PKGBUILD" "$WORK_DIR/"
cp "$SCRIPT_DIR/mv7-hid-bridge.install" "$WORK_DIR/"
cd "$WORK_DIR"

sed -i "s/^pkgver=.*/pkgver=$VERSION/" PKGBUILD
sed -i "s/^sha256sums=.*/sha256sums=('$LOCAL_SHA256')/" PKGBUILD

# Step 5: Generate .SRCINFO
echo "[3/5] Generating .SRCINFO..."
cp "/tmp/$TARBALL" "$WORK_DIR/"
makepkg --printsrcinfo > .SRCINFO

echo ""
echo "=== PKGBUILD ==="
cat PKGBUILD
echo ""
echo "=== .SRCINFO ==="
cat .SRCINFO
echo ""

# Step 6: Confirm and push
echo "[4/5] Ready to push to AUR."
echo "      Source: $TARBALL_URL"
echo "      SHA256: $LOCAL_SHA256"
echo ""
read -rp "Push to AUR? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

echo "[5/5] Pushing to AUR..."
AUR_DIR=$(mktemp -d)
git clone "$AUR_REPO" "$AUR_DIR"
cp PKGBUILD .SRCINFO mv7-hid-bridge.install "$AUR_DIR/"
cd "$AUR_DIR"
git add PKGBUILD .SRCINFO mv7-hid-bridge.install
git commit -m "Update to $VERSION"
git push

echo ""
echo "=== Done ==="
echo "Verify at: https://aur.archlinux.org/packages/mv7-hid-bridge"
