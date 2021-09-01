# Description

This is a python script for import/export proxmox vms.


# Installation

```bash
wget -O - https://raw.githubusercontent.com/orbisnull/pve-migrate-restic/main/install.sh | bash
```

# Dependencies
* [orbisnull/env-vault](https://github.com/orbisnull/env-vault)

# Usage

``` bash
bash

set +o history

#help
pve-migrate-restic -h

#export vm
pve-migrate-restic export -l https://url_vault -p secret_key -m vmid

#import vm
pve-migrate-restic import lxc -l https://url_vault -p secret_key -m vmid -r storage -t template -n name -s size

exit

```
