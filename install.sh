#!/bin/bash

dir="/opt/pve-migrate-restic"

if [[ ! -e $dir ]]; then
  mkdir $dir
fi

apt-get -yq install wget

wget -O - https://raw.githubusercontent.com/orbisnull/env-vault/main/install.sh | bash

wget -O "$dir/pve-migrate-restic.py" https://raw.githubusercontent.com/orbisnull/pve-migrate-restic/main/pve-migrate-restic.py
chmod +x "$dir/pve-migrate-restic.py"

ln -sf "$dir/pve-migrate-restic.py" /usr/local/bin/pve-migrate-restic

echo "pve-migrate-restic: Installation completed"

exit 0
