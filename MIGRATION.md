
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

#### Migration from 16.0 to 17.0

* https://oca.github.io/OpenUpgrade/040_run_migration.html
* git clone -b 17.0 git@github.com:OCA/OpenUpgrade.git
* cd OpenUpgrade # this adds openupgrade_framework and openupgrade_scripts available in addons path
* Comment out renamed module note -> project_todo in openupgrade_scripts/apriori.py
* export OPENUPGRADE_TARGET_VERSION=17.0
* activate odoo17 own.conf
* pip install git+https://github.com/OCA/openupgradelib.git@master#egg=openupgradelib
* odoo --update all --stop-after-init --load=base,web,openupgrade_framework


#### Migration from 17.0 to 18.0

* https://oca.github.io/OpenUpgrade/040_run_migration.html
* git clone -b 18.0 git@github.com:OCA/OpenUpgrade.git
* cd OpenUpgrade # this adds openupgrade_framework and openupgrade_scripts available in addons path
* export OPENUPGRADE_TARGET_VERSION=18.0
* activate odoo18 own.conf
* pip install git+https://github.com/OCA/openupgradelib.git@master#egg=openupgradelib
* odoo --update all --stop-after-init --load=base,web,openupgrade_framework --logfile=../tabularium/migrate.log
* update ir_act_window set view_mode=REPLACE(view_mode, 'tree', 'list') where view_mode ilike '%tree%';


#### Migration from 18.0 to 19.0

* https://oca.github.io/OpenUpgrade/040_run_migration.html
* git clone -b 19.0 git@github.com:OCA/OpenUpgrade.git
* cd OpenUpgrade # this adds openupgrade_framework and openupgrade_scripts available in addons path
* export OPENUPGRADE_TARGET_VERSION=19.0
* activate odoo19 own.conf
* pip install git+https://github.com/OCA/openupgradelib.git@master#egg=openupgradelib
* odoo --update all --stop-after-init --upgrade-path=$PWD/openupgrade_scripts/scripts --addons-path=$PWD --load=base,web,openupgrade_framework --logfile=../tabularium/migrate.log
* odoo -u all
