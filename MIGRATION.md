#### Migration from 13.0 to 15.0

* https://oca.github.io/OpenUpgrade/migration_details.html
* git clone -b 14.0 git@github.com:OCA/OpenUpgrade.git
* cd OpenUpgrade # this adds openupgrade_framework and openupgrade_scripts available in addons path
* export OPENUPGRADE_TARGET_VERSION=15.0
* activate odoo14
* pip install git+https://github.com/OCA/openupgradelib.git@master#egg=openupgradelib
* odoo -d eniemela_13 --update all --stop-after-init --load=base,web,openupgrade_framework
* git checkout 15.0
* activate odoo15
* pip install git+https://github.com/OCA/openupgradelib.git@master#egg=openupgradelib
* odoo -d eniemela_13 --update all --stop-after-init --load=base,web,openupgrade_framework
