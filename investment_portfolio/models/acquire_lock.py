

from odoo import models

from psycopg2 import OperationalError

class ResCompany(models.AbstractModel):
    _name = "aquire.lock.mixin"
    _description = "Aquire Lock Mixin"

    def acquire_lock(self):
        if not self.ids:
            return False
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    f"SELECT * FROM {self._table} WHERE id IN %s FOR UPDATE NOWAIT",
                    (tuple(self.ids),), log_exceptions=False,
                )
                if self.env.cr.fetchone():
                    return True
                else:
                    return False
        except OperationalError as e: # pragma: no cover
            return False
