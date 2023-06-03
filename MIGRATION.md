
# General notes
* For some reason, the migration did not move all toggl_id values. FIX:
    * `UPDATE toggl_entry SET toggl_id=toggl_id_moved0 where toggl_id IS NULL`
    * `ALTER TABLE toggl_entry DROP CONSTRAINT toggl_entry_toggl_id_uniq`

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


#### Migration from 15.0 to 16.0

* https://oca.github.io/OpenUpgrade/migration_details.html
* git clone -b 16.0 git@github.com:OCA/OpenUpgrade.git
* cd OpenUpgrade # this adds openupgrade_framework and openupgrade_scripts available in addons path
* export OPENUPGRADE_TARGET_VERSION=16.0
* activate odoo16 own.conf
* pip install git+https://github.com/OCA/openupgradelib.git@master#egg=openupgradelib
* odoo --update all --stop-after-init --load=base,web,openupgrade_framework