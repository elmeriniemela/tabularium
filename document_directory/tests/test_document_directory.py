# -*- coding: utf-8 -*-

import base64

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDocumentDirectory(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Directory = cls.env['document.directory']
        cls.Attachment = cls.env['ir.attachment']

        documents_group = cls.env.ref('document_directory.group_documents_user')
        internal_group = cls.env.ref('base.group_user')
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.documents_user = Users.create({
            'name': 'Documents User',
            'login': 'documents_user',
            'email': 'documents_user@example.com',
            'groups_id': [(6, 0, [documents_group.id])],
        })
        cls.plain_user = Users.create({
            'name': 'Plain User',
            'login': 'plain_user',
            'email': 'plain_user@example.com',
            'groups_id': [(6, 0, [internal_group.id])],
        })

    def test_attachment_and_chatter_integration(self):
        directory = self.Directory.create({'name': 'Directory A'})
        main_attachment = self.Attachment.create({
            'name': 'main.txt',
            'type': 'binary',
            'datas': base64.b64encode(b'main-content'),
        })
        directory.message_main_attachment_id = main_attachment
        self.assertEqual(directory.message_main_attachment_id, main_attachment)

        linked_attachment = self.Attachment.create({
            'name': 'linked.txt',
            'type': 'binary',
            'datas': base64.b64encode(b'linked-content'),
            'res_model': 'document.directory',
            'res_id': directory.id,
        })
        unrelated_attachment = self.Attachment.create({
            'name': 'other.txt',
            'type': 'binary',
            'datas': base64.b64encode(b'unrelated-content'),
            'res_model': 'res.partner',
            'res_id': directory.id,
        })
        self.assertIn(linked_attachment, directory.attachment_ids)
        self.assertNotIn(main_attachment, directory.attachment_ids)
        self.assertNotIn(unrelated_attachment, directory.attachment_ids)

        message = directory.message_post(body='test')
        self.assertEqual(message.model, 'document.directory')
        self.assertEqual(message.res_id, directory.id)

    def test_documents_user_access_and_plain_user_denied(self):
        directory = self.Directory.with_user(self.documents_user).create({'name': 'Allowed'})
        directory.with_user(self.documents_user).write({'name': 'Allowed Updated'})
        self.assertEqual(directory.with_user(self.documents_user).name, 'Allowed Updated')
        directory.with_user(self.documents_user).unlink()
        self.assertFalse(directory.exists())

        with self.assertRaises(RuntimeError):
            self.Directory.with_user(self.plain_user).create({'name': 'Denied'})

    def test_data_files_loaded(self):
        list_view = self.env.ref('document_directory.directory_tree')
        form_view = self.env.ref('document_directory.directory_form')
        search_view = self.env.ref('document_directory.directory_search')
        action = self.env.ref('document_directory.action_document_dirs')
        menu = self.env.ref('document_directory.root_menu')

        self.assertEqual(list_view.model, 'document.directory')
        self.assertEqual(form_view.model, 'document.directory')
        self.assertEqual(search_view.model, 'document.directory')
        self.assertEqual(action.res_model, 'document.directory')
        self.assertEqual(action.view_mode, 'list,form')
        self.assertEqual(menu.action, action)
