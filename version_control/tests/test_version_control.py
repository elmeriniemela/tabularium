import hashlib

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestVersionControl(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Version Control Test'})
        cls.message = cls.env['mail.message'].create({
            'body': '<p>Initial body</p>',
            'message_type': 'comment',
            'model': 'res.partner',
            'res_id': cls.partner.id,
            'subtype_id': cls.env.ref('mail.mt_note').id,
        })
        cls.body_field = cls.env['ir.model.fields']._get('mail.message', 'body')
        cls.subject_field = cls.env['ir.model.fields']._get('mail.message', 'subject')
        cls.comment_field = cls.env['ir.model.fields']._get('res.partner', 'comment')
        cls.env.cr.execute(
            """
            UPDATE ir_model_fields
            SET version_control = TRUE
            WHERE id = ANY(%s)
            """,
            [[cls.body_field.id, cls.comment_field.id]],
        )
        cls.env['ir.model.fields'].invalidate_model(['version_control'])

    def _create_tracking(self, field, old_value, new_value):
        values = {
            'mail_message_id': self.message.id,
            'field_id': field.id,
        }
        if field.ttype == 'char':
            values.update({
                'old_value_char': old_value,
                'new_value_char': new_value,
            })
        else:
            values.update({
                'old_value_text': old_value,
                'new_value_text': new_value,
            })
        return self.env['mail.tracking.value'].create(values)

    def test_version_control_hash_reference_and_diff(self):
        html_old = '<p>Old body</p>'
        html_new = '<p>New body</p>'
        text_old = 'Old comment line'
        text_new = 'New comment line'
        html_tracking = self._create_tracking(self.body_field, html_old, html_new)
        text_tracking = self._create_tracking(self.comment_field, text_old, text_new)

        html_version = self.env['version.control'].browse(html_tracking.id)
        text_version = self.env['version.control'].browse(text_tracking.id)

        self.assertTrue(html_version.exists())
        self.assertTrue(text_version.exists())
        self.assertEqual(html_version.reference, f'res.partner,{self.partner.id}')
        self.assertEqual(text_version.reference, f'res.partner,{self.partner.id}')

        expected_html_before = hashlib.sha1(html_old.encode('utf-8')).hexdigest()
        expected_html_after = hashlib.sha1(html_new.encode('utf-8')).hexdigest()
        self.assertEqual(html_version.version_hash_before, expected_html_before)
        self.assertEqual(html_version.version_hash_after, expected_html_after)
        self.assertEqual(
            html_version.name,
            f'{expected_html_before}...{expected_html_after}',
        )

        expected_text_before = hashlib.sha1(text_old.encode('utf-8')).hexdigest()
        expected_text_after = hashlib.sha1(text_new.encode('utf-8')).hexdigest()
        self.assertEqual(text_version.version_hash_before, expected_text_before)
        self.assertEqual(text_version.version_hash_after, expected_text_after)

        self.assertIn('--- body', html_version.diff)
        self.assertIn('+++ body', html_version.diff)
        self.assertIn('-Old body', html_version.diff)
        self.assertIn('+New body', html_version.diff)
        self.assertNotIn('<p>', html_version.diff)

        self.assertIn('--- comment', text_version.diff)
        self.assertIn('+++ comment', text_version.diff)
        self.assertIn('-Old comment line', text_version.diff)
        self.assertIn('+New comment line', text_version.diff)

    def test_mail_thread_helpers_and_field_reflection(self):
        tracking = self._create_tracking(self.body_field, '<p>old</p>', '<p>new</p>')

        self.assertEqual(self.partner.version_control_ids.ids, [tracking.id])
        self.assertEqual(self.partner.version_control_count, 1)

        mail_thread = self.env['mail.thread']
        self.assertTrue(
            mail_thread._valid_field_parameter(
                self.env['mail.message']._fields['body'],
                'version_control',
            )
        )
        self.assertTrue(
            mail_thread._valid_field_parameter(
                self.env['res.partner']._fields['comment'],
                'version_control',
            )
        )
        self.assertFalse(
            mail_thread._valid_field_parameter(
                self.env['mail.message']._fields['subject'],
                'version_control',
            )
        )

        model_id = self.env['ir.model']._get_id('mail.message')
        params = self.env['ir.model.fields']._reflect_field_params(
            self.env['mail.message']._fields['body'],
            model_id,
        )
        self.assertIn('version_control', params)
        self.assertFalse(params['version_control'])

    def test_create_tracking_values_override_branches(self):
        tracking_model = self.env['mail.tracking.value']

        html_values = tracking_model._create_tracking_values(
            '<p>old</p>',
            '<p>new</p>',
            'body',
            {'type': 'html'},
            self.message,
        )
        self.assertEqual(html_values['field_id'], self.body_field.id)
        self.assertEqual(html_values['old_value_text'], '<p>old</p>')
        self.assertEqual(html_values['new_value_text'], '<p>new</p>')

        char_values = tracking_model._create_tracking_values(
            'old subject',
            'new subject',
            'subject',
            {'type': 'char'},
            self.message,
        )
        self.assertEqual(char_values['field_id'], self.subject_field.id)
        self.assertEqual(char_values['old_value_char'], 'old subject')
        self.assertEqual(char_values['new_value_char'], 'new subject')

        with self.assertRaisesRegex(ValueError, 'Unknown field'):
            tracking_model._create_tracking_values(
                'old',
                'new',
                'field_that_does_not_exist',
                {'type': 'char'},
                self.message,
            )

    def test_tracking_value_format_model_hashes(self):
        html_tracking = self._create_tracking(
            self.body_field,
            '<p>before hash</p>',
            '<p>after hash</p>',
        )
        plain_tracking = self._create_tracking(
            self.subject_field,
            'subject before',
            'subject after',
        )

        html_formatted = html_tracking._tracking_value_format_model('mail.message')
        plain_formatted = plain_tracking._tracking_value_format_model('mail.message')
        html_version = self.env['version.control'].browse(html_tracking.id)

        self.assertEqual(
            html_formatted[0]['oldValue'],
            html_version.version_hash_before,
        )
        self.assertEqual(
            html_formatted[0]['newValue'],
            html_version.version_hash_after,
        )
        self.assertEqual(plain_formatted[0]['oldValue'], 'subject before')
        self.assertEqual(plain_formatted[0]['newValue'], 'subject after')
