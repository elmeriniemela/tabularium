
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    cr.execute("""
        SELECT array_agg(id) FROM toggl_task GROUP BY task_id HAVING COUNT(*) > 1
    """)

    for (ids, ) in cr.fetchall():
        tasks = env['toggl.task'].browse(ids).sorted()
        task = tasks[0]
        other_tasks = tasks - task
        task.entry_ids += other_tasks.entry_ids
        other_tasks.unlink()

