# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.addons.base.tests.common import TransactionCaseWithUserDemo


class TestNote(TransactionCaseWithUserDemo):

    def test_bug_lp_1156215(self):
        """ ensure any users can create new users """
        demo_user = self.user_demo
        group_erp = self.env.ref('base.group_erp_manager')

        demo_user.write({
            'groups_id': [(4, group_erp.id)],
        })

        # must not fail
        demo_user.create({
            'name': 'test bug lp:1156215',
            'login': 'lp_1156215',
        })

    def test_default_stage_is_first_by_sequence(self):
        first_stage = self.env['note.stage'].create({
            'name': 's1',
            'sequence': 1,
        })
        self.env['note.stage'].create({
            'name': 's2',
            'sequence': 20,
        })

        default_stage = self.env['note.note']._get_default_stage_id()
        self.assertEqual(default_stage, first_stage)

    def test_compute_name_and_single_record_write(self):
        note = self.env['note.note'].create({
            'memo': '<p>*Alpha*</p><p>Beta</p>',
        })
        self.assertEqual(note.name, 'Alpha')

        note.write({
            'name': 'manual-name',
            'memo': '<p>Gamma</p>',
        })
        self.assertEqual(note.name, 'manual-name')

    def test_multi_record_write(self):
        notes = self.env['note.note'].create([
            {'memo': '<p>n1</p>'},
            {'memo': '<p>n2</p>'},
        ])

        notes.write({'priority': '1'})
        self.assertEqual(set(notes.mapped('priority')), {'1'})

    def test_compute_name_keeps_existing_name(self):
        note = self.env['note.note'].create({
            'name': 'kept-name',
            'memo': '<p>*Delta*</p>',
        })

        note._compute_name()
        self.assertEqual(note.name, 'kept-name')
